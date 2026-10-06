from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from conftest import ADMIN_ID, ISBN_A, ISBN_B, OTHER_USER_ID, USER_ID, order_body


@pytest.fixture
def orders(order_db):
    """1: USER pending, 2: OTHER paid, 3: USER cancelled, 4: OTHER pending."""
    ids = [
        order_db.add_order(USER_ID, {ISBN_A: 2}),
        order_db.add_order(OTHER_USER_ID, {ISBN_A: 1, ISBN_B: 1}, estado="paid"),
        order_db.add_order(USER_ID, {ISBN_B: 1}, estado="cancelled"),
        order_db.add_order(OTHER_USER_ID, {ISBN_A: 1}),
    ]
    return ids


def test_admin_lists_all_orders_newest_first(client, admin_headers, orders):
    body = client.get("/orders", headers=admin_headers).get_json()

    assert [o["pedido_id"] for o in body["data"]] == [4, 3, 2, 1]
    assert body["pagination"] == {"limit": 50, "offset": 0, "total": 4}
    assert body["data"][2] == {
        "pedido_id": 2,
        "usuario_id": OTHER_USER_ID,
        "estado": "paid",
        "total": "30.50",
        "items_count": 2,
        "fecha_creacion": "2026-10-01T12:02:00+00:00",
        "fecha_actualizacion": "2026-10-01T12:02:00+00:00",
    }


def test_admin_pagination(client, admin_headers, orders):
    body = client.get("/orders?limit=2&offset=1", headers=admin_headers).get_json()

    assert [o["pedido_id"] for o in body["data"]] == [3, 2]
    assert body["pagination"]["total"] == 4


@pytest.mark.parametrize(
    "query,expected",
    [
        ("estado=pending", [4, 1]),
        ("estado=PAID", [2]),
        (f"usuario_id={USER_ID}", [3, 1]),
        (f"usuario_id={USER_ID}&estado=cancelled", [3]),
        ("desde=2026-10-01T12:02:00Z", [4, 3, 2]),
        ("hasta=2026-10-01T12:02:00Z", [1]),
        ("desde=2026-10-01&hasta=2026-10-01", [4, 3, 2, 1]),  # bare date = whole day
        ("hasta=2026-09-30", []),
    ],
)
def test_admin_filters(client, admin_headers, orders, query, expected):
    body = client.get(f"/orders?{query}", headers=admin_headers).get_json()

    assert [o["pedido_id"] for o in body["data"]] == expected
    assert body["pagination"]["total"] == len(expected)


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=201", "offset=-1", "estado=shipped", "usuario_id=0", "usuario_id=x", "desde=ayer",
     "desde=2026-10-02&hasta=2026-10-01"],
)
def test_admin_invalid_filters_return_400(client, admin_headers, query):
    response = client.get(f"/orders?{query}", headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


def test_orders_me_returns_only_own_orders(client, user_headers, orders):
    body = client.get("/orders/me", headers=user_headers).get_json()

    assert [o["pedido_id"] for o in body["data"]] == [3, 1]
    assert {o["usuario_id"] for o in body["data"]} == {USER_ID}


def test_orders_me_estado_filter(client, user_headers, orders):
    body = client.get("/orders/me?estado=pending", headers=user_headers).get_json()

    assert [o["pedido_id"] for o in body["data"]] == [1]


def test_orders_me_rejects_usuario_id_param(client, user_headers, orders):
    response = client.get(f"/orders/me?usuario_id={OTHER_USER_ID}", headers=user_headers)

    assert response.status_code == 400


def test_orders_me_for_admin_returns_admin_orders(client, admin_headers, orders):
    assert client.get("/orders/me", headers=admin_headers).get_json()["data"] == []


def test_user_sees_own_order_and_items(client, user_headers, orders):
    assert client.get("/orders/1", headers=user_headers).get_json()["data"]["pedido_id"] == 1

    data = client.get("/orders/1/items", headers=user_headers).get_json()["data"]
    assert data["order"]["pedido_id"] == 1
    assert data["items"] == [
        {"isbn": ISBN_A, "titulo": "Libro A", "cantidad": 2, "precio_unitario": "10.50", "subtotal": "21.00"}
    ]


@pytest.mark.parametrize("path", ["/orders/2", "/orders/2/items"])
def test_user_gets_404_for_someone_elses_order(client, user_headers, orders, path):
    response = client.get(path, headers=user_headers)

    assert response.status_code == 404
    # Identical to a missing order: existence is not revealed.
    assert response.get_json() == client.get("/orders/999", headers=user_headers).get_json()


def test_admin_sees_any_order_and_items(client, admin_headers, orders):
    assert client.get("/orders/2", headers=admin_headers).get_json()["data"]["usuario_id"] == OTHER_USER_ID
    items = client.get("/orders/2/items", headers=admin_headers).get_json()["data"]["items"]
    assert [i["isbn"] for i in items] == [ISBN_A, ISBN_B]


@pytest.mark.parametrize("path", ["/orders/999", "/orders/0", "/orders/abc", "/orders/99999999999999999999/items"])
def test_unknown_order_returns_404(client, admin_headers, orders, path):
    response = client.get(path, headers=admin_headers)

    assert response.status_code == 404
    assert response.is_json


def test_historical_price_survives_book_price_change(client, user_headers, order_db):
    client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)
    order_db.books[ISBN_A]["precio"] = Decimal("99.00")

    items = client.get("/orders/1/items", headers=user_headers).get_json()["data"]["items"]

    assert items[0]["precio_unitario"] == "10.50"
    assert client.get("/orders/1", headers=user_headers).get_json()["data"]["total"] == "10.50"
