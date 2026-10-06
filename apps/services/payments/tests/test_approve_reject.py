from __future__ import annotations

import copy

import psycopg
import pytest

from conftest import USER_ID, FakeUniqueViolation


def _state(db):
    return copy.deepcopy((db.orders, db.payments, db.stock))


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

def test_approve_marks_payment_and_order_atomically(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)
    stock_before = dict(pay_db.stock)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["payment"]["estado"] == "approved"
    assert data["payment"]["monto"] == "21.00"
    assert data["payment"]["fecha_pago"] is not None  # ck_pagos_fecha_pago
    assert data["order"] == {"pedido_id": pedido, "estado": "paid", "total": "21.00"}
    assert pay_db.orders[pedido]["estado"] == "paid"
    assert pay_db.stock == stock_before


def test_approve_twice_is_409(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)
    client.post(f"/payments/{pago}/approve", headers=admin_headers)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_ALREADY_APPROVED"


def test_second_attempt_of_a_paid_order_cannot_be_approved(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    first, second = pay_db.add_payment(pedido), pay_db.add_payment(pedido)
    client.post(f"/payments/{first}/approve", headers=admin_headers)
    before = _state(pay_db)

    response = client.post(f"/payments/{second}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_NOT_PAYABLE"
    assert response.get_json()["details"] == {"order_estado": "paid"}
    assert _state(pay_db) == before
    # The leftover attempt can still be rejected.
    assert client.post(f"/payments/{second}/reject", headers=admin_headers).status_code == 200


@pytest.mark.parametrize("estado", ["cancelled", "completed"])
def test_cannot_approve_when_order_is_no_longer_pending(client, admin_headers, pay_db, estado):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)
    pay_db.orders[pedido]["estado"] = estado  # e.g. Orders cancelled it meanwhile

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_NOT_PAYABLE"
    assert pay_db.payments[pago]["estado"] == "pending"


def test_amount_mismatch_is_409(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido, monto="20.00")

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_AMOUNT_MISMATCH"
    assert pay_db.orders[pedido]["estado"] == "pending"


@pytest.mark.parametrize("estado,code", [("rejected", "INVALID_PAYMENT_TRANSITION"), ("refunded", "PAYMENT_ALREADY_REFUNDED")])
def test_cannot_approve_final_payments(client, admin_headers, pay_db, estado, code):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido, estado=estado)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == code


def test_unknown_payment_is_404(client, admin_headers):
    assert client.post("/payments/999/approve", headers=admin_headers).get_json()["code"] == "PAYMENT_NOT_FOUND"


def test_failure_changing_the_order_rolls_back_the_approval(client, admin_headers, pay_db, monkeypatch):
    from repositories import payment_repository

    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    def broken(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(payment_repository, "set_order_status", broken)
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 500
    assert _state(pay_db) == before  # payment NOT left approved with order pending


def test_failure_updating_the_payment_leaves_order_pending(client, admin_headers, pay_db, monkeypatch):
    from repositories import payment_repository

    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    def broken(*_a, **_k):
        raise psycopg.errors.InternalError_("disk full")

    monkeypatch.setattr(payment_repository, "set_payment_status", broken)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 500
    assert "disk full" not in response.get_data(as_text=True)
    assert pay_db.orders[pedido]["estado"] == "pending"


def test_unique_approved_index_race_is_409(client, admin_headers, pay_db, monkeypatch):
    from repositories import payment_repository

    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    def raced(*_a, **_k):
        raise FakeUniqueViolation("duplicate", "ux_pagos_un_aprobado_por_pedido")

    monkeypatch.setattr(payment_repository, "set_payment_status", raced)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_ALREADY_APPROVED"
    assert pay_db.orders[pedido]["estado"] == "pending"


@pytest.mark.parametrize("error", [psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure])
def test_lock_conflicts_are_409(client, admin_headers, pay_db, monkeypatch, error):
    from repositories import payment_repository

    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    def conflict(*_a, **_k):
        raise error("conflict")

    monkeypatch.setattr(payment_repository, "lock_order", conflict)

    response = client.post(f"/payments/{pago}/approve", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "TRANSACTION_CONFLICT"


@pytest.mark.parametrize("body", [{"estado": "approved"}, {"monto": "1"}, {"x": 1}])
def test_action_endpoints_take_no_body(client, admin_headers, pay_db, body):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    response = client.post(f"/payments/{pago}/approve", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert pay_db.payments[pago]["estado"] == "pending"


def test_action_endpoints_accept_empty_object(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)

    assert client.post(f"/payments/{pago}/approve", json={}, headers=admin_headers).status_code == 200


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

def test_reject_keeps_attempt_and_order_pending(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)
    stock_before = dict(pay_db.stock)

    response = client.post(f"/payments/{pago}/reject", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["payment"]["estado"] == "rejected"
    assert data["payment"]["fecha_pago"] is None
    assert data["order"]["estado"] == "pending"
    assert pay_db.orders[pedido]["estado"] == "pending"
    assert pay_db.stock == stock_before
    assert pago in pay_db.payments  # history kept


def test_new_attempt_after_rejection_can_be_approved(client, admin_headers, user_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    rejected = pay_db.add_payment(pedido)
    client.post(f"/payments/{rejected}/reject", headers=admin_headers)

    retry = client.post("/payments", json={"pedido_id": pedido, "metodo_pago": "debit_card"}, headers=user_headers)
    approved = client.post(f"/payments/{retry.get_json()['data']['pago_id']}/approve", headers=admin_headers)

    assert approved.status_code == 200
    assert pay_db.orders[pedido]["estado"] == "paid"
    assert sorted(p["estado"] for p in pay_db.payments.values()) == ["approved", "rejected"]


@pytest.mark.parametrize("estado,code", [
    ("approved", "INVALID_PAYMENT_TRANSITION"),
    ("rejected", "INVALID_PAYMENT_TRANSITION"),
    ("refunded", "PAYMENT_ALREADY_REFUNDED"),
])
def test_only_pending_payments_can_be_rejected(client, admin_headers, pay_db, estado, code):
    pedido = pay_db.add_order(USER_ID, "21.00", estado="paid" if estado == "approved" else "pending")
    pago = pay_db.add_payment(pedido, estado=estado)
    before = _state(pay_db)

    response = client.post(f"/payments/{pago}/reject", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == code
    assert _state(pay_db) == before


def test_reject_works_for_attempts_of_a_cancelled_order(client, admin_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")
    pago = pay_db.add_payment(pedido)
    pay_db.orders[pedido]["estado"] = "cancelled"  # cancelled by Orders

    response = client.post(f"/payments/{pago}/reject", headers=admin_headers)

    assert response.status_code == 200
    assert pay_db.orders[pedido]["estado"] == "cancelled"
