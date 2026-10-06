from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import OTHER_USER_ID, USER_ID


@pytest.fixture
def data(pay_db):
    """Orders 1 (USER) and 2 (OTHER). Payments: 1 rejected, 2 approved (order 1), 3 pending (order 2)."""
    o1 = pay_db.add_order(USER_ID, "21.00", estado="paid")
    o2 = pay_db.add_order(OTHER_USER_ID, "7.25")
    pay_db.add_payment(o1, estado="rejected", metodo="debit_card")
    pay_db.add_payment(o1, estado="approved", metodo="credit_card")
    pay_db.add_payment(o2, estado="pending", metodo="cash")
    return o1, o2


def test_admin_lists_all_newest_first(client, admin_headers, data):
    body = client.get("/payments", headers=admin_headers).get_json()

    assert [p["pago_id"] for p in body["data"]] == [3, 2, 1]
    assert body["pagination"] == {"limit": 50, "offset": 0, "total": 3}
    assert body["data"][1] == {
        "pago_id": 2,
        "pedido_id": 1,
        "usuario_id": USER_ID,
        "monto": "21.00",
        "metodo_pago": "credit_card",
        "estado": "approved",
        "referencia": "SEED-2",
        "fecha_pago": "2026-10-01T12:02:00+00:00",
        "fecha_creacion": "2026-10-01T12:02:00+00:00",
        "fecha_actualizacion": "2026-10-01T12:02:00+00:00",
    }


@pytest.mark.parametrize(
    "query,expected",
    [
        ("pedido_id=1", [2, 1]),
        ("estado=approved", [2]),
        ("metodo_pago=CASH", [3]),
        ("desde=2026-10-01T12:02:00Z", [3, 2]),
        ("hasta=2026-10-01T12:02:00Z", [1]),
        ("desde=2026-10-01&hasta=2026-10-01", [3, 2, 1]),
        ("limit=1&offset=1", [2]),
    ],
)
def test_admin_filters(client, admin_headers, data, query, expected):
    assert [p["pago_id"] for p in client.get(f"/payments?{query}", headers=admin_headers).get_json()["data"]] == expected


@pytest.mark.parametrize("query", ["estado=paid", "metodo_pago=paypal", "pedido_id=0", "limit=500", "usuario_id=2", "desde=x"])
def test_invalid_filters_return_400(client, admin_headers, data, query):
    assert client.get(f"/payments?{query}", headers=admin_headers).status_code == 400


def test_payments_me_only_returns_own(client, user_headers, other_headers, data):
    mine = client.get("/payments/me", headers=user_headers).get_json()["data"]
    theirs = client.get("/payments/me", headers=other_headers).get_json()["data"]

    assert [p["pago_id"] for p in mine] == [2, 1]
    assert [p["pago_id"] for p in theirs] == [3]


def test_payments_me_rejects_usuario_id(client, user_headers, data):
    assert client.get(f"/payments/me?usuario_id={OTHER_USER_ID}", headers=user_headers).status_code == 400


def test_payments_me_filter_by_other_users_order_returns_nothing(client, user_headers, data):
    assert client.get("/payments/me?pedido_id=2", headers=user_headers).get_json()["data"] == []


def test_get_own_payment(client, user_headers, data):
    assert client.get("/payments/2", headers=user_headers).get_json()["data"]["estado"] == "approved"


def test_someone_elses_payment_is_404_like_a_missing_one(client, user_headers, data):
    foreign = client.get("/payments/3", headers=user_headers)
    missing = client.get("/payments/999", headers=user_headers)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.get_json() == missing.get_json()


def test_admin_gets_any_payment(client, admin_headers, data):
    assert client.get("/payments/3", headers=admin_headers).get_json()["data"]["usuario_id"] == OTHER_USER_ID


def test_order_payments_for_owner_and_admin(client, user_headers, admin_headers, data):
    own = client.get("/orders/1/payments", headers=user_headers).get_json()["data"]
    assert own["order"] == {"pedido_id": 1, "estado": "paid", "total": "21.00"}
    assert [p["pago_id"] for p in own["payments"]] == [2, 1]

    assert client.get("/orders/2/payments", headers=user_headers).get_json()["code"] == "ORDER_NOT_FOUND"
    assert client.get("/orders/2/payments", headers=admin_headers).status_code == 200
    assert client.get("/orders/999/payments", headers=admin_headers).status_code == 404


def test_amount_is_frozen_even_if_the_order_total_changes(client, user_headers, pay_db, data):
    pay_db.orders[1]["total"] = Decimal("99.00")

    assert client.get("/payments/2", headers=user_headers).get_json()["data"]["monto"] == "21.00"


@pytest.mark.parametrize("path", ["/payments/0", "/payments/abc", "/payments/99999999999999999999"])
def test_invalid_ids_are_404_json(client, admin_headers, path):
    response = client.get(path, headers=admin_headers)

    assert response.status_code == 404
    assert response.is_json
