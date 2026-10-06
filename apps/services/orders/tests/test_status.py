from __future__ import annotations

import copy

import pytest

from conftest import ISBN_A, ISBN_B, OTHER_USER_ID, USER_ID
from services import status


def _patch(client, headers, pedido_id, estado):
    return client.patch(f"/orders/{pedido_id}/status", json={"estado": estado}, headers=headers)


def test_cancel_pending_order_restores_exact_stock(client, admin_headers, order_db, fake_redis):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 2, ISBN_B: 1})
    order_db.books[ISBN_A]["stock"] = 3  # as if the order had taken 2 of 5
    order_db.books[ISBN_B]["stock"] = 0
    fake_redis.store[f"books:{ISBN_A}"] = "{}"

    response = _patch(client, admin_headers, pedido_id, "cancelled")

    assert response.status_code == 200
    assert response.get_json()["data"]["estado"] == "cancelled"
    assert order_db.books[ISBN_A]["stock"] == 5
    assert order_db.books[ISBN_B]["stock"] == 1
    assert order_db.locked[-1] == [ISBN_A, ISBN_B]
    assert f"books:{ISBN_A}" not in fake_redis.store  # Books cache invalidated
    # History is kept: the lines are still there.
    assert len([k for k in order_db.items if k[0] == pedido_id]) == 2


def test_cancelling_twice_never_restores_stock_twice(client, admin_headers, order_db):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 2})
    assert _patch(client, admin_headers, pedido_id, "cancelled").status_code == 200
    stock_after_first = order_db.books[ISBN_A]["stock"]

    response = _patch(client, admin_headers, pedido_id, "cancelled")

    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_ALREADY_CANCELLED"
    assert order_db.books[ISBN_A]["stock"] == stock_after_first


def test_paid_to_completed(client, admin_headers, order_db):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1}, estado="paid")
    stock_before = order_db.books[ISBN_A]["stock"]

    response = _patch(client, admin_headers, pedido_id, "completed")

    assert response.status_code == 200
    assert response.get_json()["data"]["estado"] == "completed"
    assert order_db.books[ISBN_A]["stock"] == stock_before


@pytest.mark.parametrize(
    "current,requested",
    [
        ("pending", "paid"),  # Payments only
        ("paid", "cancelled"),  # Payments only (refund)
        ("pending", "completed"),
        ("pending", "pending"),
        ("paid", "paid"),
        ("paid", "pending"),
        ("completed", "cancelled"),
        ("completed", "pending"),
        ("completed", "completed"),
        ("cancelled", "pending"),
        ("cancelled", "paid"),
        ("cancelled", "completed"),
    ],
)
def test_invalid_transitions_return_409_and_change_nothing(client, admin_headers, order_db, current, requested):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1}, estado=current)
    before = copy.deepcopy((order_db.books, order_db.orders))

    response = _patch(client, admin_headers, pedido_id, requested)

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "INVALID_STATUS_TRANSITION"
    assert body["details"] == {"from": current, "to": requested}
    assert (order_db.books, order_db.orders) == before


def test_payment_only_transitions_explain_why(client, admin_headers, order_db):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1})

    message = _patch(client, admin_headers, pedido_id, "paid").get_json()["message"]

    assert "Payments" in message


def test_user_cannot_change_status(client, user_headers, order_db):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1})

    response = _patch(client, user_headers, pedido_id, "cancelled")

    assert response.status_code == 403
    assert order_db.orders[pedido_id]["estado"] == "pending"


def test_unknown_order_returns_404(client, admin_headers):
    assert _patch(client, admin_headers, 999, "cancelled").get_json()["code"] == "ORDER_NOT_FOUND"


@pytest.mark.parametrize(
    "body",
    [{"estado": "shipped"}, {"estado": ""}, {"estado": None}, {"estado": 1}, {}, {"status": "cancelled"},
     {"estado": "cancelled", "total": "0"}],
)
def test_invalid_status_body_returns_400(client, admin_headers, order_db, body):
    pedido_id = order_db.add_order(OTHER_USER_ID, {ISBN_A: 1})

    response = client.patch(f"/orders/{pedido_id}/status", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert order_db.orders[pedido_id]["estado"] == "pending"


def test_status_is_case_insensitive(client, admin_headers, order_db):
    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1})

    assert _patch(client, admin_headers, pedido_id, " CANCELLED ").status_code == 200


def test_failure_while_restoring_stock_rolls_back_the_status(client, admin_headers, order_db, monkeypatch):
    from repositories import order_repository

    pedido_id = order_db.add_order(USER_ID, {ISBN_A: 1, ISBN_B: 1})
    real_change = order_db.change_stock

    def fail_on_b(conn, isbn, delta):
        if isbn == ISBN_B:
            raise RuntimeError("boom")
        real_change(conn, isbn, delta)

    monkeypatch.setattr(order_repository, "change_stock", fail_on_b)
    before = copy.deepcopy((order_db.books, order_db.orders))

    response = _patch(client, admin_headers, pedido_id, "cancelled")

    assert response.status_code == 500
    assert (order_db.books, order_db.orders) == before


def test_status_module_matches_the_schema_states():
    assert status.STATUSES == ("pending", "paid", "completed", "cancelled")
    assert status.ORDERS_SERVICE_TRANSITIONS <= status.ORDER_TRANSITIONS
    assert status.restores_stock("pending", "cancelled")
    assert status.restores_stock("paid", "cancelled")
    assert not status.restores_stock("cancelled", "cancelled")
    assert not status.restores_stock("paid", "completed")
