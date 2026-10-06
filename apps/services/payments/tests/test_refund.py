from __future__ import annotations

import copy

import pytest

from conftest import ISBN_A, ISBN_B, USER_ID


def _paid_order(db, items=None):
    pedido = db.add_order(USER_ID, "41.00", items=items or [{"isbn": ISBN_B, "cantidad": 1}, {"isbn": ISBN_A, "cantidad": 2}])
    pago = db.add_payment(pedido, estado="approved")
    db.orders[pedido]["estado"] = "paid"
    return pedido, pago


def _state(db):
    return copy.deepcopy((db.orders, db.payments, db.stock))


def test_refund_cancels_order_and_restores_exact_stock(client, admin_headers, pay_db, fake_redis):
    pedido, pago = _paid_order(pay_db)
    fake_redis.store.update({f"books:{ISBN_A}": "{}", f"books:{ISBN_B}": "{}", "books:list:all": "[]", "jwt:revoked:x": "1"})

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["payment"]["estado"] == "refunded"
    assert data["payment"]["fecha_pago"] is not None  # kept (ck_pagos_fecha_pago)
    assert data["order"]["estado"] == "cancelled"
    assert data["restocked"] == [{"isbn": ISBN_A, "cantidad": 2}, {"isbn": ISBN_B, "cantidad": 1}]
    assert pay_db.stock == {ISBN_A: 5, ISBN_B: 1}
    assert pay_db.locked_books == [[ISBN_A, ISBN_B]]  # ISBN order, like Orders
    # Books cache dropped for those books and every list; nothing else.
    assert sorted(fake_redis.store) == ["jwt:revoked:x"]


def test_second_refund_never_restores_stock_again(client, admin_headers, pay_db):
    _pedido, pago = _paid_order(pay_db)
    client.post(f"/payments/{pago}/refund", headers=admin_headers)
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_ALREADY_REFUNDED"
    assert _state(pay_db) == before


@pytest.mark.parametrize("estado", ["pending", "rejected"])
def test_only_approved_payments_can_be_refunded(client, admin_headers, pay_db, estado):
    pedido = pay_db.add_order(USER_ID, "41.00")
    pago = pay_db.add_payment(pedido, estado=estado)
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "REFUND_NOT_ALLOWED"
    assert _state(pay_db) == before


def test_completed_order_cannot_be_refunded(client, admin_headers, pay_db):
    pedido, pago = _paid_order(pay_db)
    pay_db.orders[pedido]["estado"] = "completed"
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "REFUND_NOT_ALLOWED"
    assert body["details"] == {"payment_estado": "approved", "order_estado": "completed"}
    assert _state(pay_db) == before


def test_failure_during_refund_rolls_back_everything(client, admin_headers, pay_db, fake_redis, monkeypatch):
    from repositories import payment_repository

    _pedido, pago = _paid_order(pay_db)
    fake_redis.store[f"books:{ISBN_A}"] = "{}"

    def broken(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(payment_repository, "set_order_status", broken)
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 500
    assert _state(pay_db) == before  # stock, payment and order unchanged
    assert f"books:{ISBN_A}" in fake_redis.store  # no invalidation without commit


def test_cache_failure_after_commit_does_not_undo_the_refund(client, admin_headers, pay_db, monkeypatch):
    from library_shared.redis_client import RedisGateway

    pedido, pago = _paid_order(pay_db)
    monkeypatch.setattr(RedisGateway, "cache_invalidate", lambda self, keys=(), patterns=(): False)

    response = client.post(f"/payments/{pago}/refund", headers=admin_headers)

    assert response.status_code == 200
    assert pay_db.payments[pago]["estado"] == "refunded"
    assert pay_db.orders[pedido]["estado"] == "cancelled"


def test_user_cannot_refund(client, user_headers, pay_db):
    _pedido, pago = _paid_order(pay_db)

    assert client.post(f"/payments/{pago}/refund", headers=user_headers).status_code == 403
    assert pay_db.payments[pago]["estado"] == "approved"
