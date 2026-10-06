"""
401 / 403 / 503 on every write endpoint. All of it is library_shared
(require_roles); this file checks that each Authors write is wired to it
and that nothing is written when access is denied.
"""

from __future__ import annotations

import copy
import time

import jwt
import pytest

from conftest import ADMIN_ID, BORGES, ISBN_FICCIONES, ISBN_HUERFANO, JWT_SECRET, SIN_LIBROS, bearer
from library_shared.token_store import revoke_token


WRITE_ENDPOINTS = [
    ("post", "/authors", {"nombre": "N", "apellido": "A"}),
    ("put", f"/authors/{BORGES}", {"nombre": "N", "apellido": "A", "pais": None}),
    ("patch", f"/authors/{BORGES}", {"nombre": "N"}),
    ("delete", f"/authors/{SIN_LIBROS}", None),
    ("post", f"/authors/{BORGES}/books/{ISBN_HUERFANO}", None),
    ("delete", f"/authors/{BORGES}/books/{ISBN_FICCIONES}", None),
]


def _call(client, method, url, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


def _state(db):
    return copy.deepcopy((db.authors, db.books, db.relations))


@pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
def test_writes_without_token_return_401(client, author_db, method, url, body):
    before = _state(author_db)

    response = _call(client, method, url, body)

    assert response.status_code == 401
    assert response.get_json()["code"] == "MISSING_TOKEN"
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert _state(author_db) == before


@pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
def test_writes_with_user_role_return_403(client, author_db, user_headers, method, url, body):
    before = _state(author_db)

    response = _call(client, method, url, body, user_headers)

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"
    assert _state(author_db) == before


@pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
def test_writes_with_admin_are_allowed(client, admin_headers, method, url, body):
    response = _call(client, method, url, body, admin_headers)

    assert response.status_code in (200, 201)


@pytest.mark.parametrize("method,url,body", WRITE_ENDPOINTS)
def test_redis_down_on_writes_returns_503_and_writes_nothing(
    client, fake_redis, author_db, admin_headers, method, url, body
):
    fake_redis.down = True
    before = _state(author_db)

    response = _call(client, method, url, body, admin_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "AUTH_BACKEND_UNAVAILABLE"
    assert "redis-test-password" not in response.get_data(as_text=True)
    assert _state(author_db) == before


@pytest.mark.parametrize("header", ["Token abc", "Bearer", "Bearer a b", "Basic dXNlcjpwYXNz"])
def test_malformed_authorization_header_returns_401(client, header):
    response = client.post("/authors", json={"nombre": "N", "apellido": "A"}, headers={"Authorization": header})

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_AUTHORIZATION_HEADER"


def test_expired_token_returns_401(client, make_token):
    issued = make_token(ADMIN_ID, 2, now=int(time.time()) - 3600)

    response = client.post("/authors", json={"nombre": "N", "apellido": "A"}, headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_EXPIRED"


def test_revoked_token_returns_401(client, gateway, make_token):
    issued = make_token(ADMIN_ID, 2)
    revoke_token(gateway, issued.claims)

    response = client.post("/authors", json={"nombre": "N", "apellido": "A"}, headers=bearer(issued))

    assert response.status_code == 401
    assert response.get_json()["code"] == "TOKEN_REVOKED"


def test_refresh_token_used_as_access_returns_401(client, make_token):
    refresh = make_token(ADMIN_ID, 2, refresh=True)

    response = client.post("/authors", json={"nombre": "N", "apellido": "A"}, headers=bearer(refresh))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_token_signed_with_other_secret_returns_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "x" * 32, "iat": now, "exp": now + 600, "type": "access"}
    forged = jwt.encode(payload, "another-secret-that-is-long-enough-0123456789", algorithm="HS256")

    response = client.delete(f"/authors/{SIN_LIBROS}", headers=bearer(forged))

    assert response.status_code == 401
    assert response.get_json()["code"] == "INVALID_TOKEN"


def test_token_with_other_algorithm_returns_401(client):
    now = int(time.time())
    payload = {"user_id": ADMIN_ID, "role_id": 2, "jti": "y" * 32, "iat": now, "exp": now + 600, "type": "access"}
    other_alg = jwt.encode(payload, JWT_SECRET * 2, algorithm="HS512")

    assert client.delete(f"/authors/{SIN_LIBROS}", headers=bearer(other_alg)).status_code == 401


def test_validation_runs_only_after_authentication(client):
    # An invalid body from an anonymous caller is still 401, never 400.
    assert client.post("/authors", json={"foo": 1}).status_code == 401
