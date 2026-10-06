"""401 / 403 / 503 on every endpoint; 405 for edit/delete of history."""

from __future__ import annotations

import copy
import time

import jwt
import pytest

from conftest import ADMIN_ID, JWT_SECRET, USER_ID, bearer


@pytest.fixture
def seeded(pay_db):
    pedido = pay_db.add_order(USER_ID, "21.00")  # 1
    pay_db.add_payment(pedido)  # pago 1 pending
    return pay_db


ENDPOINTS = [
    ("get", "/payments", None),
    ("get", "/payments/me", None),
    ("get", "/payments/1", None),
    ("get", "/orders/1/payments", None),
    ("post", "/payments", {"pedido_id": 1, "metodo_pago": "cash"}),
    ("post", "/payments/1/approve", None),
    ("post", "/payments/1/reject", None),
    ("post", "/payments/1/refund", None),
]
ADMIN_ONLY = [e for e in ENDPOINTS if e[1] == "/payments" and e[0] == "get" or e[1].endswith(("/approve", "/reject", "/refund"))]


def _call(client, method, url, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def _state(db):
    return copy.deepcopy((db.orders, db.payments, db.stock))


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
    assert _state(seeded) == before


@pytest.mark.parametrize("method,url,body", ADMIN_ONLY)
def test_admin_only_endpoints_reject_user(client, seeded, user_headers, method, url, body):
    before = _state(seeded)

    response = _call(client, method, url, body, user_headers)

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
    assert _state(seeded) == before


def test_admin_only_list_is_complete(client, seeded):
    assert {e[1] for e in ADMIN_ONLY} == {"/payments", "/payments/1/approve", "/payments/1/reject", "/payments/1/refund"}


def test_admin_lists_all(client, seeded, admin_headers):
    assert client.get("/payments", headers=admin_headers).status_code == 200


def test_expired_token_returns_401(client, make_token):
    issued = make_token(USER_ID, 1, now=int(time.time()) - 3600)

    response = client.get("/payments/me", headers=bearer(issued))

    assert response.get_json()["code"] == "TOKEN_EXPIRED"


def test_revoked_token_returns_401(client, gateway, make_token, seeded):
    from library_shared.token_store import revoke_token

    issued = make_token(ADMIN_ID, 2)
    revoke_token(gateway, issued.claims)

    response = client.post("/payments/1/approve", headers=bearer(issued))

    assert response.get_json()["code"] == "TOKEN_REVOKED"
    assert seeded.payments[1]["estado"] == "pending"


def test_refresh_token_used_as_access_returns_401(client, make_token):
    response = client.get("/payments/me", headers=bearer(make_token(USER_ID, 1, refresh=True)))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_forged_and_other_algorithm_tokens_return_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "x" * 32, "iat": now, "exp": now + 600, "type": "access"}

    forged = jwt.encode(payload, "another-secret-that-is-long-enough-0123456789", algorithm="HS256")
    other_alg = jwt.encode(payload, JWT_SECRET * 2, algorithm="HS512")

    assert client.get("/payments", headers=bearer(forged)).status_code == 401
    assert client.get("/payments", headers=bearer(other_alg)).status_code == 401


@pytest.mark.parametrize("method", ["delete", "put", "patch"])
def test_payments_cannot_be_edited_or_deleted(client, seeded, admin_headers, method):
    before = _state(seeded)

    response = getattr(client, method)("/payments/1", json={"estado": "approved"}, headers=admin_headers)

    assert response.status_code == 405
    assert response.is_json
    assert _state(seeded) == before
