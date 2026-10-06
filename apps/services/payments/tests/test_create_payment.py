from __future__ import annotations

import copy

import pytest

from conftest import ADMIN_ID, INACTIVE_ID, OTHER_USER_ID, USER_ID, bearer


@pytest.fixture
def order(pay_db):
    return pay_db.add_order(USER_ID, "21.00")


def _body(pedido_id, **extra):
    return {"pedido_id": pedido_id, "metodo_pago": "credit_card", **extra}


def test_owner_registers_pending_attempt_with_order_total(client, user_headers, pay_db, order):
    response = client.post("/payments", json=_body(order), headers=user_headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["pedido_id"] == order
    assert data["usuario_id"] == USER_ID
    assert data["monto"] == "21.00"  # pedidos.total, not the client
    assert data["estado"] == "pending"  # DEFAULT
    assert data["fecha_pago"] is None
    assert data["metodo_pago"] == "credit_card"
    assert data["referencia"].startswith("PAY-")
    # Registering an attempt does not touch the order or the stock.
    assert pay_db.orders[order]["estado"] == "pending"
    assert pay_db.stock == {"9780000000001": 3, "9780000000002": 0}


def test_client_referencia_is_kept(client, user_headers, order):
    data = client.post("/payments", json=_body(order, referencia=" TRX-2026/10:001 "), headers=user_headers).get_json()["data"]

    assert data["referencia"] == "TRX-2026/10:001"


def test_duplicate_referencia_returns_409(client, user_headers, pay_db, order):
    client.post("/payments", json=_body(order, referencia="TRX-1"), headers=user_headers)

    response = client.post("/payments", json=_body(order, referencia="TRX-1"), headers=user_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_REFERENCE_EXISTS"
    assert len(pay_db.payments) == 1


def test_several_pending_attempts_are_allowed(client, user_headers, pay_db, order):
    for _ in range(2):
        assert client.post("/payments", json=_body(order), headers=user_headers).status_code == 201
    assert len(pay_db.payments) == 2


def test_admin_can_register_for_any_order(client, admin_headers, order):
    response = client.post("/payments", json=_body(order, metodo_pago="cash"), headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["usuario_id"] == USER_ID  # still the order owner


def test_someone_elses_order_is_404(client, other_headers, pay_db, order):
    response = client.post("/payments", json=_body(order), headers=other_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "ORDER_NOT_FOUND"
    assert pay_db.payments == {}


def test_missing_order_is_404(client, user_headers):
    assert client.post("/payments", json=_body(999), headers=user_headers).get_json()["code"] == "ORDER_NOT_FOUND"


@pytest.mark.parametrize("estado", ["paid", "completed", "cancelled"])
def test_only_pending_orders_are_payable(client, user_headers, pay_db, estado):
    pedido = pay_db.add_order(USER_ID, "10.00", estado=estado)

    response = client.post("/payments", json=_body(pedido), headers=user_headers)

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "ORDER_NOT_PAYABLE"
    assert body["details"] == {"order_estado": estado}
    assert pay_db.payments == {}


def test_zero_total_order_is_not_payable(client, user_headers, pay_db):
    pedido = pay_db.add_order(USER_ID, "0.00")

    response = client.post("/payments", json=_body(pedido), headers=user_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ORDER_NOT_PAYABLE"


def test_inactive_user_cannot_register_payments(client, make_token, pay_db):
    pedido = pay_db.add_order(INACTIVE_ID, "10.00")

    response = client.post("/payments", json=_body(pedido), headers=bearer(make_token(INACTIVE_ID, 1)))

    assert response.status_code == 403
    assert response.get_json()["code"] == "USER_INACTIVE"


@pytest.mark.parametrize(
    "field,value",
    [
        ("monto", "0.01"),
        ("estado", "approved"),
        ("status", "approved"),
        ("usuario_id", OTHER_USER_ID),
        ("pago_id", 7),
        ("fecha_pago", "2026-01-01"),
        ("fecha_creacion", "2026-01-01"),
        ("fecha_actualizacion", "2026-01-01"),
    ],
)
def test_server_managed_fields_return_400(client, user_headers, pay_db, order, field, value):
    response = client.post("/payments", json=_body(order, **{field: value}), headers=user_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"
    assert response.get_json()["details"] == {"fields": [field]}
    assert pay_db.payments == {}


def test_unknown_fields_return_400(client, user_headers, order):
    response = client.post("/payments", json=_body(order, tarjeta="4111"), headers=user_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "UNKNOWN_FIELDS"


@pytest.mark.parametrize("metodo", ["paypal", "", None, 1, "tarjeta"])
def test_invalid_method_returns_400(client, user_headers, order, metodo):
    response = client.post("/payments", json={"pedido_id": order, "metodo_pago": metodo}, headers=user_headers)

    assert response.status_code == 400
    assert "metodo_pago" in response.get_json()["message"]


def test_method_is_case_insensitive(client, user_headers, order):
    response = client.post("/payments", json={"pedido_id": order, "metodo_pago": " Bank_Transfer "}, headers=user_headers)

    assert response.get_json()["data"]["metodo_pago"] == "bank_transfer"


@pytest.mark.parametrize("referencia", ["", "   ", "con espacio", "x" * 101, 5, "-empieza-con-guion", "ñandú"])
def test_invalid_referencia_returns_400(client, user_headers, order, referencia):
    response = client.post("/payments", json=_body(order, referencia=referencia), headers=user_headers)

    assert response.status_code == 400
    assert "referencia" in response.get_json()["message"]


@pytest.mark.parametrize("pedido_id", [0, -1, "1", 1.0, True, None])
def test_invalid_pedido_id_returns_400(client, user_headers, pedido_id):
    response = client.post("/payments", json={"pedido_id": pedido_id, "metodo_pago": "cash"}, headers=user_headers)

    assert response.status_code == 400


@pytest.mark.parametrize("kwargs", [{"data": "x", "content_type": "application/json"}, {"json": [1]}, {}])
def test_non_object_body_returns_400(client, user_headers, kwargs):
    assert client.post("/payments", headers=user_headers, **kwargs).status_code == 400


def test_failure_after_insert_rolls_back(client, user_headers, pay_db, order, monkeypatch):
    from repositories import payment_repository

    def broken(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(payment_repository, "get_payment", broken)
    before = copy.deepcopy(pay_db.payments)

    response = client.post("/payments", json=_body(order), headers=user_headers)

    assert response.status_code == 500
    assert pay_db.payments == before
