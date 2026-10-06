"""
Any failure inside the creation transaction leaves NOTHING behind (fake
database with snapshot/rollback). The same scenarios run against real
PostgreSQL in test_integration_postgres.py.
"""

from __future__ import annotations

import copy

import psycopg
import pytest

from conftest import ISBN_A, ISBN_B, ISBN_MISSING, FakeCheckViolation, order_body


def _state(db):
    return copy.deepcopy((db.books, db.orders, db.items))


def test_failure_on_second_book_creates_nothing(client, user_headers, order_db):
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1), (ISBN_MISSING, 1)), headers=user_headers)

    assert response.status_code == 404
    assert _state(order_db) == before


def test_failure_inserting_second_line_rolls_back_everything(client, user_headers, order_db, monkeypatch):
    from repositories import order_repository

    real_insert = order_db.insert_item

    def insert_then_fail(conn, pedido_id, isbn, cantidad, precio):
        if isbn == ISBN_B:
            raise psycopg.errors.InternalError_("disk full")
        real_insert(conn, pedido_id, isbn, cantidad, precio)

    monkeypatch.setattr(order_repository, "insert_item", insert_then_fail)
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1), (ISBN_B, 1)), headers=user_headers)

    assert response.status_code == 500
    assert response.get_json()["code"] == "INTERNAL_ERROR"
    assert "disk full" not in response.get_data(as_text=True)
    assert _state(order_db) == before
    assert order_db.rollbacks == 1


def test_failure_updating_second_stock_rolls_back_everything(client, user_headers, order_db, monkeypatch):
    from repositories import order_repository

    real_change = order_db.change_stock

    def change_then_fail(conn, isbn, delta):
        if isbn == ISBN_B:
            raise RuntimeError("boom")
        real_change(conn, isbn, delta)

    monkeypatch.setattr(order_repository, "change_stock", change_then_fail)
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 2), (ISBN_B, 1)), headers=user_headers)

    assert response.status_code == 500
    assert _state(order_db) == before  # ISBN_A stock untouched, no order, no lines


def test_stock_check_violation_is_409_and_rolls_back(client, user_headers, order_db, monkeypatch):
    """libros_stock_check as the last barrier (e.g. stock edited without locks)."""
    from repositories import order_repository

    def violate(_conn, _isbn, _delta):
        raise FakeCheckViolation("check", "libros_stock_check")

    monkeypatch.setattr(order_repository, "change_stock", violate)
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "INSUFFICIENT_STOCK"
    assert _state(order_db) == before


@pytest.mark.parametrize(
    "error,code",
    [
        (psycopg.errors.DeadlockDetected, "TRANSACTION_CONFLICT"),
        (psycopg.errors.SerializationFailure, "TRANSACTION_CONFLICT"),
    ],
)
def test_deadlock_or_serialization_failure_is_409_and_rolls_back(client, user_headers, order_db, monkeypatch, error, code):
    from repositories import order_repository

    def fail(*_a, **_k):
        raise error("conflict")

    monkeypatch.setattr(order_repository, "insert_order", fail)
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == code
    assert _state(order_db) == before


def test_database_down_is_503(client, user_headers, order_db):
    order_db.down = True

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"
    assert "db-test-password" not in response.get_data(as_text=True)
