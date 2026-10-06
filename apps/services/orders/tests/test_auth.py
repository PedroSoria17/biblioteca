"""401 / 403 / 503 on every endpoint (all of them are protected)."""

from __future__ import annotations

import copy
import time

import jwt
import pytest

from conftest import ADMIN_ID, ISBN_A, JWT_SECRET, USER_ID, bearer, order_body


ENDPOINTS = [
    ("get", "/orders", None),
    ("get", "/orders/me", None),
    ("get", "/orders/1", None),
    ("get", "/orders/1/items", None),
    ("post", "/orders", order_body((ISBN_A, 1))),
    ("patch", "/orders/1/status", {"estado": "cancelled"}),
]


def _call(client, method, url, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def _state(db):
    return copy.deepcopy((db.books, db.orders, db.items))


@pytest.fixture
def seeded(order_db):
    order_db.add_order(USER_ID, {ISBN_A: 1})  # pedido 1
    return order_db


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_every_endpoint_requires_a_token(client, seeded, method, url, body):
    before = _state(seeded)

    response = _call(client, method, url, body)

    assert response.status_code == 401
    assert response.get_json()["code"] == "MISSING_TOKEN"
    assert _state(seeded) == before


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_redis_down_returns_503_and_changes_nothing(client, seeded, fake_redis, admin_headers, method, url, body):
    fake_redis.down = True
    before = _state(seeded)

    response = _call(client, method, url, body, admin_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "AUTH_BACKEND_UNAVAILABLE"
    assert "redis-test-password" not in response.get_data(as_text=True)
    assert _state(seeded) == before


@pytest.mark.parametrize(
    "method,url,body",
    [("get", "/orders", None), ("patch", "/orders/1/status", {"estado": "cancelled"})],
)
def test_admin_only_endpoints_reject_user_with_403(client, seeded, user_headers, method, url, body):
    before = _state(seeded)

    response = _call(client, method, url, body, user_headers)

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
    assert _state(seeded) == before


def test_user_can_create_and_read_own_orders(client, seeded, user_headers):
    assert client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers).status_code == 201
    assert client.get("/orders/me", headers=user_headers).status_code == 200
    assert client.get("/orders/1", headers=user_headers).status_code == 200
    assert client.get("/orders/1/items", headers=user_headers).status_code == 200


def test_admin_can_list_all(client, seeded, admin_headers):
    assert client.get("/orders", headers=admin_headers).status_code == 200


def test_expired_token_returns_401(client, make_token):
    issued = make_token(USER_ID, 1, now=int(time.time()) - 3600)

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_EXPIRED"


def test_revoked_token_returns_401(client, gateway, make_token, order_db):
    from library_shared.token_store import revoke_token

    issued = make_token(USER_ID, 1)
    revoke_token(gateway, issued.claims)

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_REVOKED"
    assert order_db.orders == {}


def test_refresh_token_used_as_access_returns_401(client, make_token):
    response = client.get("/orders/me", headers=bearer(make_token(USER_ID, 1, refresh=True)))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_forged_and_other_algorithm_tokens_return_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "x" * 32, "iat": now, "exp": now + 600, "type": "access"}
    forged = jwt.encode(payload, "another-secret-that-is-long-enough-0123456789", algorithm="HS256")
    other_alg = jwt.encode(payload, JWT_SECRET * 2, algorithm="HS512")

    assert client.get("/orders", headers=bearer(forged)).status_code == 401
    assert client.get("/orders", headers=bearer(other_alg)).status_code == 401


def test_there_is_no_delete_endpoint(client, seeded, admin_headers):
    response = client.delete("/orders/1", headers=admin_headers)

    assert response.status_code == 405
    assert response.is_json
    assert 1 in seeded.orders
