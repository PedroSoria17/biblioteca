"""
End-to-end tests of /login, /refresh, /logout, /session and /health with
JWT + Redis, through the real Flask app (create_app) and library_shared.
PostgreSQL and Redis are replaced by in-memory fakes (see conftest.py).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import xml.etree.ElementTree as ET

import jwt
import pytest

from library_shared import keys
from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.roles import ROLE_ADMIN, ROLE_USER
from library_shared.settings import load_jwt_settings
from library_shared.token_store import store_refresh_token, store_session
from library_shared.redis_client import RedisGateway

from tests.conftest import JWT_SECRET, REDIS_PASSWORD, USER_PASSWORD


ACCESS_TTL = 20 * 60
REFRESH_TTL = 7 * 24 * 3600


def _login(client, email="user@example.com", password=USER_PASSWORD, fmt="json"):
    return client.post(f"/login?format={fmt}", json={"email": email, "password": password})


def _tokens(client, email="user@example.com"):
    resp = _login(client, email)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _decode(token):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def _refresh(client, token, fmt="json"):
    return client.post(f"/refresh?format={fmt}", headers=_bearer(token))


def _logout(client, token, fmt="json"):
    return client.post(f"/logout?format={fmt}", headers=_bearer(token))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def test_login_success_returns_tokens_and_user(client):
    body = _tokens(client, "admin@example.com")

    assert body["success"] is True
    assert body["message"] == "Login successful"
    assert body["user"] == {"id": 1, "email": "admin@example.com", "role_id": ROLE_ADMIN}
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == ACCESS_TTL
    assert body["refresh_expires_in"] == REFRESH_TTL
    assert body["access_token"] and body["refresh_token"]


def test_access_token_claims(client):
    body = _tokens(client, "admin@example.com")

    header = jwt.get_unverified_header(body["access_token"])
    claims = _decode(body["access_token"])

    assert header["alg"] == "HS256"
    assert claims["user_id"] == 1
    assert claims["role_id"] == ROLE_ADMIN
    assert claims["type"] == "access"
    assert claims["jti"] and claims["sid"]
    assert claims["exp"] - claims["iat"] == ACCESS_TTL


def test_refresh_token_claims(client):
    body = _tokens(client)

    access = _decode(body["access_token"])
    refresh = _decode(body["refresh_token"])

    assert refresh["type"] == "refresh"
    assert refresh["user_id"] == 2 and refresh["role_id"] == ROLE_USER
    assert refresh["sid"] == access["sid"]
    assert refresh["jti"] != access["jti"]
    assert refresh["exp"] - refresh["iat"] == REFRESH_TTL


def test_login_stores_session_and_refresh_in_redis(client, fake_redis):
    body = _tokens(client)
    access = _decode(body["access_token"])
    refresh = _decode(body["refresh_token"])

    session_key = keys.session_key(access["sid"])
    refresh_key = keys.refresh_token_key(refresh["jti"])

    assert fake_redis.ttls[session_key] == REFRESH_TTL
    assert REFRESH_TTL - 2 <= fake_redis.ttls[refresh_key] <= REFRESH_TTL

    session = json.loads(fake_redis.get(session_key))
    assert session["user_id"] == 2
    assert session["role_id"] == ROLE_USER
    assert session["refresh_jti"] == refresh["jti"]
    assert json.loads(fake_redis.get(refresh_key)) == {"user_id": 2, "role_id": ROLE_USER, "sid": access["sid"]}


def test_redis_never_stores_passwords_hashes_or_full_tokens(client, fake_redis, user_db):
    body = _tokens(client)
    stored = " ".join(value for value, _exp in fake_redis.store.values())

    assert USER_PASSWORD not in stored
    assert user_db.users[2]["password_hash"] not in stored
    assert body["access_token"] not in stored
    assert body["refresh_token"] not in stored
    assert JWT_SECRET not in stored


def test_login_xml_is_default_and_contains_tokens(client):
    resp = client.post("/login", json={"email": "user@example.com", "password": USER_PASSWORD})

    assert resp.status_code == 200
    assert resp.mimetype == "application/xml"
    root = ET.fromstring(resp.data)
    assert root.tag == "response"
    assert root.findtext("success") == "true"
    assert root.findtext("token_type") == "Bearer"
    assert root.findtext("expires_in") == str(ACCESS_TTL)
    assert root.findtext("user/role_id") == str(ROLE_USER)
    assert _decode(root.findtext("access_token"))["type"] == "access"
    assert _decode(root.findtext("refresh_token"))["type"] == "refresh"


@pytest.mark.parametrize(
    "email,password",
    [
        ("missing@example.com", USER_PASSWORD),
        ("user@example.com", "wrong-password"),
        ("inactive@example.com", USER_PASSWORD),
    ],
)
def test_login_failures_are_401_without_tokens_or_redis_state(client, fake_redis, email, password):
    resp = _login(client, email, password)

    assert resp.status_code == 401
    body = resp.get_json()
    assert body == {"success": False, "message": "Invalid credentials"}
    assert fake_redis.store == {}


def test_login_validation_error_is_still_400(client):
    resp = client.post("/login?format=json", json={"email": "user@example.com"})

    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_login_with_redis_down_is_503_without_tokens(client, fake_redis):
    fake_redis.down = True

    resp = _login(client)

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["code"] == "AUTH_BACKEND_UNAVAILABLE"
    assert "access_token" not in body and "refresh_token" not in body


def test_login_redis_failure_midway_leaves_no_usable_session(client, fake_redis):
    # Session SET succeeds, refresh SET fails: no tokens, session cleaned up.
    fake_redis.fail_on_set_number = 2

    resp = _login(client)

    assert resp.status_code == 503
    assert "access_token" not in resp.get_json()
    assert fake_redis.keys_with_prefix("auth:") == []


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

def test_refresh_rotates_both_tokens(client, fake_redis):
    first = _tokens(client)
    old_access = _decode(first["access_token"])
    old_refresh = _decode(first["refresh_token"])

    resp = _refresh(client, first["refresh_token"])

    assert resp.status_code == 200
    body = resp.get_json()
    new_access = _decode(body["access_token"])
    new_refresh = _decode(body["refresh_token"])

    assert body["token_type"] == "Bearer" and body["expires_in"] == ACCESS_TTL
    assert new_access["type"] == "access" and new_refresh["type"] == "refresh"
    assert new_access["jti"] != old_access["jti"]
    assert new_refresh["jti"] != old_refresh["jti"]
    assert new_access["sid"] == new_refresh["sid"] == old_access["sid"]

    assert keys.refresh_token_key(old_refresh["jti"]) not in fake_redis.store
    assert keys.refresh_token_key(new_refresh["jti"]) in fake_redis.store
    session = json.loads(fake_redis.get(keys.session_key(old_access["sid"])))
    assert session["refresh_jti"] == new_refresh["jti"]


def test_new_refresh_token_keeps_working(client):
    first = _tokens(client)
    second = _refresh(client, first["refresh_token"]).get_json()

    third = _refresh(client, second["refresh_token"])

    assert third.status_code == 200


def test_refresh_token_cannot_be_used_twice(client):
    first = _tokens(client)
    assert _refresh(client, first["refresh_token"]).status_code == 200

    resp = _refresh(client, first["refresh_token"])

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_REVOKED"


def test_concurrent_refresh_with_same_token_only_one_succeeds(app):
    first = _tokens(app.test_client())
    barrier = threading.Barrier(8)
    statuses: list[int] = []

    def worker():
        client = app.test_client()
        barrier.wait()
        statuses.append(_refresh(client, first["refresh_token"]).status_code)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(statuses) == [200] + [401] * 7


def test_expired_refresh_token_is_401(client, fake_redis, env):
    settings = load_jwt_settings(env)
    expired = create_refresh_token(settings, 2, ROLE_USER, session_id="s-old", now=int(time.time()) - REFRESH_TTL - 60)

    resp = _refresh(client, expired.token)

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_EXPIRED"


def test_access_token_is_rejected_by_refresh(client):
    body = _tokens(client)

    resp = _refresh(client, body["access_token"])

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer"}])
def test_refresh_without_valid_bearer_header_is_401(client, headers):
    resp = client.post("/refresh?format=json", headers=headers)

    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Bearer")


def test_refresh_with_forged_signature_is_401(client):
    body = _tokens(client)
    claims = _decode(body["refresh_token"])
    forged = jwt.encode(claims, "attacker-secret-key-that-is-long-enough-000", algorithm="HS256")

    assert _refresh(client, forged).status_code == 401


def test_refresh_token_without_redis_entry_is_rejected(client, env, fake_redis):
    # Valid signature, but never registered in Redis (or already revoked).
    settings = load_jwt_settings(env)
    gateway = RedisGateway(fake_redis)
    refresh = create_refresh_token(settings, 2, ROLE_USER, session_id="sid-x")
    store_session(gateway, "sid-x", {"user_id": 2, "refresh_jti": refresh.claims.jti}, 60)

    resp = _refresh(client, refresh.token)

    assert resp.status_code == 401


def test_refresh_requires_live_session(client, fake_redis):
    body = _tokens(client)
    sid = _decode(body["access_token"])["sid"]
    fake_redis.delete(keys.session_key(sid))

    assert _refresh(client, body["refresh_token"]).status_code == 401


def test_refresh_with_redis_down_is_503_and_does_not_burn_the_token(client, fake_redis):
    body = _tokens(client)
    fake_redis.down = True

    resp = _refresh(client, body["refresh_token"])

    assert resp.status_code == 503
    assert resp.get_json()["code"] == "AUTH_BACKEND_UNAVAILABLE"
    assert "access_token" not in resp.get_json()

    fake_redis.down = False
    assert _refresh(client, body["refresh_token"]).status_code == 200


def test_refresh_with_database_down_does_not_burn_the_token(client, user_db):
    body = _tokens(client)
    user_db.down = True

    resp = _refresh(client, body["refresh_token"])

    assert resp.status_code == 500
    assert "access_token" not in resp.get_json()

    user_db.down = False
    assert _refresh(client, body["refresh_token"]).status_code == 200


def test_refresh_uses_current_role_from_database(client, user_db, fake_redis):
    body = _tokens(client, "admin@example.com")
    assert _decode(body["access_token"])["role_id"] == ROLE_ADMIN

    user_db.users[1]["role_id"] = ROLE_USER  # demoted in PostgreSQL after login

    refreshed = _refresh(client, body["refresh_token"]).get_json()

    assert _decode(refreshed["access_token"])["role_id"] == ROLE_USER
    assert _decode(refreshed["refresh_token"])["role_id"] == ROLE_USER
    assert refreshed["user"]["role_id"] == ROLE_USER
    sid = _decode(refreshed["access_token"])["sid"]
    assert json.loads(fake_redis.get(keys.session_key(sid)))["role_id"] == ROLE_USER


def test_refresh_for_deactivated_user_ends_session(client, user_db, fake_redis):
    body = _tokens(client)
    sid = _decode(body["access_token"])["sid"]
    user_db.users[2]["activo"] = False

    resp = _refresh(client, body["refresh_token"])

    assert resp.status_code == 401
    assert keys.session_key(sid) not in fake_redis.store
    assert fake_redis.keys_with_prefix("auth:refresh:") == []


def test_refresh_xml_response(client):
    body = _tokens(client)

    resp = _refresh(client, body["refresh_token"], fmt="xml")

    assert resp.status_code == 200
    root = ET.fromstring(resp.data)
    assert root.findtext("message") == "Token refreshed"
    assert root.findtext("token_type") == "Bearer"
    assert _decode(root.findtext("access_token"))["type"] == "access"


def test_refresh_error_xml_response(client):
    resp = client.post("/refresh", headers=_bearer("not-a-jwt"))

    assert resp.status_code == 401
    assert resp.mimetype == "application/xml"
    root = ET.fromstring(resp.data)
    assert root.findtext("success") == "false"
    assert root.findtext("code") == "INVALID_TOKEN"


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

def test_logout_revokes_access_and_removes_session_and_refresh(client, fake_redis):
    body = _tokens(client)
    access = _decode(body["access_token"])
    refresh = _decode(body["refresh_token"])

    resp = _logout(client, body["access_token"])

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "message": "Logged out"}

    revoked_key = keys.revoked_jwt_key(access["jti"])
    assert revoked_key in fake_redis.store
    assert abs(fake_redis.ttls[revoked_key] - (access["exp"] - time.time())) <= 2
    assert keys.session_key(access["sid"]) not in fake_redis.store
    assert keys.refresh_token_key(refresh["jti"]) not in fake_redis.store


def test_after_logout_access_and_refresh_no_longer_work(client):
    body = _tokens(client)
    assert _logout(client, body["access_token"]).status_code == 200

    session = client.get("/session?format=json", headers=_bearer(body["access_token"]))
    second_logout = _logout(client, body["access_token"])
    refresh = _refresh(client, body["refresh_token"])

    assert session.status_code == 401 and session.get_json()["code"] == "TOKEN_REVOKED"
    assert second_logout.status_code == 401 and second_logout.get_json()["code"] == "TOKEN_REVOKED"
    assert refresh.status_code == 401


def test_logout_after_refresh_revokes_the_rotated_refresh(client, fake_redis):
    first = _tokens(client)
    second = _refresh(client, first["refresh_token"]).get_json()

    assert _logout(client, second["access_token"]).status_code == 200

    assert _refresh(client, second["refresh_token"]).status_code == 401
    assert fake_redis.keys_with_prefix("auth:") == []


def test_logout_does_not_affect_other_sessions(client):
    first = _tokens(client)
    other = _tokens(client)

    assert _logout(client, first["access_token"]).status_code == 200

    assert client.get("/session?format=json", headers=_bearer(other["access_token"])).status_code == 200
    assert _refresh(client, other["refresh_token"]).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Token abc"}])
def test_logout_without_access_token_is_401(client, headers):
    resp = client.post("/logout?format=json", headers=headers)

    assert resp.status_code == 401


def test_logout_with_refresh_token_is_401(client):
    body = _tokens(client)

    assert _logout(client, body["refresh_token"]).status_code == 401


def test_logout_with_expired_access_token_is_401(client, env):
    settings = load_jwt_settings(env)
    expired = create_access_token(settings, 2, ROLE_USER, session_id="s", now=int(time.time()) - 3600)

    resp = _logout(client, expired.token)

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_EXPIRED"


def test_logout_with_redis_down_is_503(client, fake_redis):
    body = _tokens(client)
    fake_redis.down = True

    resp = _logout(client, body["access_token"])

    assert resp.status_code == 503
    assert resp.get_json()["code"] == "AUTH_BACKEND_UNAVAILABLE"


def test_logout_xml_response(client):
    body = _tokens(client)

    resp = _logout(client, body["access_token"], fmt="xml")

    assert resp.status_code == 200
    root = ET.fromstring(resp.data)
    assert root.findtext("success") == "true"
    assert root.findtext("message") == "Logged out"


# ---------------------------------------------------------------------------
# /session, /health, logs, CORS, config
# ---------------------------------------------------------------------------

def test_session_without_token_keeps_anonymous_contract(client):
    resp = client.get("/session?format=json")

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "authenticated": False}


def test_session_with_valid_access_token(client):
    body = _tokens(client)

    resp = client.get("/session?format=json", headers=_bearer(body["access_token"]))

    assert resp.status_code == 200
    assert resp.get_json() == {
        "success": True,
        "authenticated": True,
        "user": {"id": 2, "email": "user@example.com", "role_id": ROLE_USER},
    }


def test_login_does_not_set_cookie_session_anymore(client):
    resp = _login(client)

    assert "Set-Cookie" not in resp.headers


def test_health_reports_postgres_and_redis(client):
    resp = client.get("/health?format=json")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "success": True,
        "service": "login",
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }


def test_health_with_redis_down_is_503_without_secrets(client, fake_redis):
    fake_redis.down = True

    resp = client.get("/health?format=json")

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["redis"] == "unavailable"
    assert body["database"] == "connected"
    assert REDIS_PASSWORD not in resp.get_data(as_text=True)
    assert "6379" not in resp.get_data(as_text=True)


def test_health_with_database_down(client, user_db):
    user_db.down = True

    resp = client.get("/health")

    assert resp.status_code == 503
    root = ET.fromstring(resp.data)
    assert root.findtext("database") == "unavailable"
    assert root.findtext("redis") == "connected"


def test_logs_never_contain_secrets_or_tokens(client, fake_redis, caplog):
    with caplog.at_level(logging.DEBUG):
        body = _tokens(client)
        refreshed = _refresh(client, body["refresh_token"]).get_json()
        _logout(client, refreshed["access_token"])
        fake_redis.down = True
        _login(client)

    text = caplog.text
    for secret in (
        USER_PASSWORD,
        JWT_SECRET,
        REDIS_PASSWORD,
        body["access_token"],
        body["refresh_token"],
        refreshed["access_token"],
        refreshed["refresh_token"],
    ):
        assert secret not in text


def test_cors_allows_only_configured_origin(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "http://evil.example"})

    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in denied.headers


@pytest.mark.parametrize("missing", ["JWT_SECRET_KEY", "REDIS_URL"])
def test_app_refuses_to_start_without_security_config(env, monkeypatch, missing):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.delenv(missing)

    with pytest.raises(ConfigurationError):
        create_app()


def test_cors_wildcard_rejected_in_production(env, monkeypatch):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ConfigurationError):
        create_app()
