from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from conftest import ADMIN_ID, INACTIVE_ID, ISBN_A, ISBN_B, ISBN_C, ISBN_MISSING, USER_ID, bearer, order_body


def _state(db):
    return copy.deepcopy((db.books, db.orders, db.items))


def test_create_order_with_one_book(client, user_headers, order_db):
    response = client.post("/orders", json=order_body((ISBN_A, 2)), headers=user_headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["pedido_id"] == 1
    assert data["usuario_id"] == USER_ID  # from the token
    assert data["estado"] == "pending"  # column DEFAULT
    assert data["total"] == "21.00"  # computed by the (fake) trigger
    assert data["items"] == [
        {"isbn": ISBN_A, "titulo": "Libro A", "cantidad": 2, "precio_unitario": "10.50", "subtotal": "21.00"}
    ]
    assert order_db.books[ISBN_A]["stock"] == 3


def test_create_order_with_several_books(client, user_headers, order_db):
    response = client.post("/orders", json=order_body((ISBN_B, 1), (ISBN_A, 1)), headers=user_headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert [i["isbn"] for i in data["items"]] == [ISBN_A, ISBN_B]
    assert data["total"] == "30.50"
    assert data["items_count"] == 2
    assert order_db.books[ISBN_A]["stock"] == 4
    assert order_db.books[ISBN_B]["stock"] == 0


def test_books_are_locked_in_isbn_order(client, user_headers, order_db):
    client.post("/orders", json=order_body((ISBN_B, 1), (ISBN_A, 1)), headers=user_headers)

    assert order_db.locked == [[ISBN_A, ISBN_B]]


def test_repeated_isbn_is_consolidated_into_one_line(client, user_headers, order_db):
    response = client.post("/orders", json=order_body((ISBN_A, 2), (ISBN_A, 3)), headers=user_headers)

    assert response.status_code == 201
    items = response.get_json()["data"]["items"]
    assert items == [
        {"isbn": ISBN_A, "titulo": "Libro A", "cantidad": 5, "precio_unitario": "10.50", "subtotal": "52.50"}
    ]
    assert order_db.books[ISBN_A]["stock"] == 0


def test_isbn_is_normalized_before_consolidating(client, user_headers, order_db):
    body = {"items": [{"isbn": f" {ISBN_A} ", "cantidad": 1}, {"isbn": ISBN_A, "cantidad": 1}]}

    response = client.post("/orders", json=body, headers=user_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["items"][0]["cantidad"] == 2


def test_exact_stock_is_allowed_and_leaves_zero(client, user_headers, order_db):
    response = client.post("/orders", json=order_body((ISBN_B, 1)), headers=user_headers)

    assert response.status_code == 201
    assert order_db.books[ISBN_B]["stock"] == 0


def test_insufficient_stock_returns_409_and_changes_nothing(client, user_headers, order_db):
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1), (ISBN_B, 2), (ISBN_C, 1)), headers=user_headers)

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "INSUFFICIENT_STOCK"
    assert body["details"]["items"] == [
        {"isbn": ISBN_B, "requested": 2, "available": 1},
        {"isbn": ISBN_C, "requested": 1, "available": 0},
    ]
    assert _state(order_db) == before


def test_missing_book_returns_404_and_changes_nothing(client, user_headers, order_db):
    before = _state(order_db)

    response = client.post("/orders", json=order_body((ISBN_A, 1), (ISBN_MISSING, 1)), headers=user_headers)

    assert response.status_code == 404
    body = response.get_json()
    assert body["code"] == "BOOK_NOT_FOUND"
    assert body["details"] == {"isbns": [ISBN_MISSING]}
    assert _state(order_db) == before


def test_inactive_user_cannot_create_orders(client, make_token, order_db):
    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=bearer(make_token(INACTIVE_ID, 1)))

    assert response.status_code == 403
    assert response.get_json()["code"] == "USER_INACTIVE"
    assert order_db.orders == {}
    assert order_db.books[ISBN_A]["stock"] == 5


def test_deleted_user_cannot_create_orders(client, make_token, order_db):
    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=bearer(make_token(999, 1)))

    assert response.status_code == 403
    assert response.get_json()["code"] == "USER_INACTIVE"


def test_admin_creates_orders_for_itself(client, admin_headers):
    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["usuario_id"] == ADMIN_ID


# ---------------------------------------------------------------------------
# Validation (always before touching the database)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {"items": None},
        {"items": "x"},
        {"items": {"isbn": ISBN_A, "cantidad": 1}},
        {},
        {"items": [ISBN_A]},
    ],
)
def test_invalid_items_list_returns_400(client, user_headers, order_db, body):
    response = client.post("/orders", json=body, headers=user_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"
    assert order_db.orders == {}


@pytest.mark.parametrize("cantidad", [0, -1, 1.5, 2.0, "2", True, None, 10_001])
def test_invalid_cantidad_returns_400(client, user_headers, order_db, cantidad):
    response = client.post("/orders", json={"items": [{"isbn": ISBN_A, "cantidad": cantidad}]}, headers=user_headers)

    assert response.status_code == 400
    assert "cantidad" in response.get_json()["message"]
    assert order_db.orders == {}


def test_consolidated_cantidad_over_limit_returns_400(client, user_headers):
    response = client.post("/orders", json=order_body((ISBN_A, 6000), (ISBN_A, 6000)), headers=user_headers)

    assert response.status_code == 400


@pytest.mark.parametrize("isbn", ["", "   ", "abc", "97800000000011234567890", 9780000000001, None])
def test_invalid_isbn_returns_400(client, user_headers, isbn):
    response = client.post("/orders", json={"items": [{"isbn": isbn, "cantidad": 1}]}, headers=user_headers)

    assert response.status_code == 400
    assert "isbn" in response.get_json()["message"]


@pytest.mark.parametrize("missing", ["isbn", "cantidad"])
def test_item_missing_field_returns_400(client, user_headers, missing):
    item = {"isbn": ISBN_A, "cantidad": 1}
    item.pop(missing)

    response = client.post("/orders", json={"items": [item]}, headers=user_headers)

    assert response.status_code == 400
    assert missing in response.get_json()["message"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("usuario_id", 1),
        ("pedido_id", 5),
        ("total", "0.01"),
        ("estado", "paid"),
        ("status", "paid"),
        ("fecha_creacion", "2020-01-01"),
        ("fecha_actualizacion", "2020-01-01"),
    ],
)
def test_server_managed_order_fields_return_400(client, user_headers, order_db, field, value):
    body = {**order_body((ISBN_A, 1)), field: value}

    response = client.post("/orders", json=body, headers=user_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"
    assert response.get_json()["details"] == {"fields": [field]}
    assert order_db.orders == {}


@pytest.mark.parametrize("field", ["precio_unitario", "precio", "subtotal", "pedido_id"])
def test_server_managed_item_fields_return_400(client, user_headers, order_db, field):
    body = {"items": [{"isbn": ISBN_A, "cantidad": 1, field: "0.01"}]}

    response = client.post("/orders", json=body, headers=user_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"
    assert response.get_json()["details"] == {"fields": [f"items[0].{field}"]}


def test_unknown_fields_return_400(client, user_headers):
    response = client.post("/orders", json={**order_body((ISBN_A, 1)), "cupon": "X"}, headers=user_headers)
    assert response.status_code == 400
    assert response.get_json()["code"] == "UNKNOWN_FIELDS"

    response = client.post(
        "/orders", json={"items": [{"isbn": ISBN_A, "cantidad": 1, "quantity": 1}]}, headers=user_headers
    )
    assert response.get_json()["details"] == {"fields": ["items[0].quantity"]}


def test_too_many_entries_returns_400(client, user_headers):
    response = client.post("/orders", json=order_body(*[(ISBN_A, 1)] * 101), headers=user_headers)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "kwargs",
    [{"data": "not json", "content_type": "application/json"}, {"json": ["a"]}, {}],
)
def test_non_object_body_returns_400(client, user_headers, kwargs):
    response = client.post("/orders", headers=user_headers, **kwargs)

    assert response.status_code == 400


def test_price_comes_from_the_database_not_the_client(client, user_headers, order_db):
    order_db.books[ISBN_A]["precio"] = Decimal("99.99")

    data = client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers).get_json()["data"]

    assert data["items"][0]["precio_unitario"] == "99.99"
    assert data["total"] == "99.99"


def test_successful_order_invalidates_books_cache(client, user_headers, fake_redis):
    fake_redis.store.update(
        {
            f"books:{ISBN_A}": "{}",
            "books:list:all": "[]",
            "books:list:q=libro": "[]",
            f"books:{ISBN_B}": "{}",
            "jwt:revoked:abc": "1",
        }
    )

    client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    assert sorted(fake_redis.store) == [f"books:{ISBN_B}", "jwt:revoked:abc"]


def test_failed_order_does_not_touch_books_cache(client, user_headers, fake_redis):
    fake_redis.store[f"books:{ISBN_B}"] = "{}"

    client.post("/orders", json=order_body((ISBN_B, 5)), headers=user_headers)

    assert f"books:{ISBN_B}" in fake_redis.store
