"""
401 / 403 / 503 behavior. Everything here goes through library_shared
(require_auth / require_roles); this file checks that every Users endpoint
is wired to it correctly.
"""

from __future__ import annotations

import time

import jwt
import pytest

from conftest import ADMIN_ID, JWT_SECRET, USER_ID, bearer
from library_shared.token_store import revoke_token


ADMIN_ENDPOINTS = [
    ("get", "/users", None),
    ("get", f"/users/{USER_ID}", None),
    ("post", "/users", {"nombre_completo": "N", "email": "n@example.com", "password": "Password123"}),
    ("put", f"/users/{USER_ID}", {"nombre_completo": "N", "email": "n@example.com", "role_id": 1, "activo": True}),
    ("patch", f"/users/{USER_ID}", {"nombre_completo": "N"}),
    ("delete", f"/users/{USER_ID}", None),
]


def _call(client, method, url, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


@pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
def test_admin_endpoints_without_token_return_401(client, user_db, method, url, body):
    before = {k: dict(v) for k, v in user_db.users.items()}

    response = _call(client, method, url, body)

    assert response.status_code == 401
    assert response.get_json()["code"] == "MISSING_TOKEN"
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert user_db.users == before


@pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
def test_admin_endpoints_with_user_role_return_403(client, user_db, user_headers, method, url, body):
    before = {k: dict(v) for k, v in user_db.users.items()}

    response = _call(client, method, url, body, user_headers)

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
    assert user_db.users == before


def test_get_users_with_admin_returns_200(client, admin_headers):
    response = client.get("/users", headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_users_me_without_token_returns_401(client):
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer a b", "Basic dXNlcjpwYXNz"])
def test_malformed_authorization_header_returns_401(client, header):
    response = client.get("/users", headers={"Authorization": header})

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_AUTHORIZATION_HEADER"


def test_expired_token_returns_401(client, make_token):
    issued = make_token(ADMIN_ID, 2, now=int(time.time()) - 3600)

    response = client.get("/users", headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_EXPIRED"


def test_revoked_token_returns_401(client, gateway, make_token):
    issued = make_token(ADMIN_ID, 2)
    revoke_token(gateway, issued.claims)

    response = client.get("/users", headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_REVOKED"


def test_refresh_token_used_as_access_returns_401(client, make_token):
    refresh = make_token(ADMIN_ID, 2, refresh=True)

    response = client.get("/users", headers=bearer(refresh))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_token_signed_with_other_secret_returns_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "x" * 32, "iat": now, "exp": now + 600, "type": "access"}
    forged = jwt.encode(payload, "another-secret-that-is-long-enough-0123456789", algorithm="HS256")

    response = client.get("/users", headers=bearer(forged))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_token_with_other_algorithm_returns_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "y" * 32, "iat": now, "exp": now + 600, "type": "access"}
    other_alg = jwt.encode(payload, JWT_SECRET * 2, algorithm="HS512")

    response = client.get("/users", headers=bearer(other_alg))

    assert response.status_code == 401


def test_token_missing_role_claim_returns_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "jti": "z" * 32, "iat": now, "exp": now + 600, "type": "access"}
    incomplete = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    assert client.get("/users", headers=bearer(incomplete)).status_code == 401


@pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
def test_redis_down_returns_503_and_never_runs_the_operation(
    client, fake_redis, user_db, admin_headers, method, url, body
):
    fake_redis.down = True
    before = {k: dict(v) for k, v in user_db.users.items()}

    response = _call(client, method, url, body, admin_headers)

    assert response.status_code == 503
    data = response.get_json()
    assert data["code"] == "AUTH_BACKEND_UNAVAILABLE"
    # No secret from the Redis error message reaches the client.
    assert "redis-test-password" not in response.get_data(as_text=True)
    assert user_db.users == before


def test_redis_down_on_users_me_returns_503(client, fake_redis, user_headers):
    fake_redis.down = True

    response = client.get("/users/me", headers=user_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "AUTH_BACKEND_UNAVAILABLE"


def test_403_is_never_returned_to_unauthenticated_caller_even_if_redis_is_down(client, fake_redis):
    fake_redis.down = True

    assert client.get("/users").status_code == 401
