from __future__ import annotations

import pytest

from conftest import DB_PASSWORD, ISBN_A, JWT_SECRET, REDIS_PASSWORD, USER_ID, order_body


def _assert_no_secrets(text: str) -> None:
    for secret in (DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD):
        assert secret not in text


def test_health_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "service": "orders",
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }


def test_health_unavailable_without_redis(client, fake_redis):
    fake_redis.down = True

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "unavailable"
    assert response.get_json()["redis"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_health_unavailable_without_database(client, order_db):
    order_db.down = True

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["database"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_cors_allows_configured_origin_only(client):
    allowed = client.options("/orders", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    denied = client.options("/orders", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})

    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_wildcard_cors_rejected_in_production(env, monkeypatch, gateway):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ConfigurationError):
        create_app(redis_gateway=gateway)


@pytest.mark.parametrize("name", ["JWT_SECRET_KEY", "REDIS_URL", "DB_PASSWORD", "DB_NAME"])
def test_missing_required_configuration_fails_fast(env, monkeypatch, gateway, name):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.delenv(name)

    with pytest.raises(ConfigurationError):
        create_app(redis_gateway=gateway)


def test_default_port_is_5004(env, monkeypatch):
    from config import get_settings

    monkeypatch.delenv("FLASK_PORT", raising=False)

    assert get_settings().flask_port == 5004


def test_logs_contain_ids_only(client, user_headers, caplog):
    caplog.set_level("INFO")

    client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert f"Order 1 created by user {USER_ID} (1 line(s))" in logged
    assert user_headers["Authorization"].split()[1] not in logged


def test_cache_invalidation_failure_does_not_undo_the_order(client, user_headers, order_db, fake_redis, monkeypatch):
    # Redis answers the revocation check, then fails during invalidation.
    from library_shared.redis_client import RedisGateway

    monkeypatch.setattr(RedisGateway, "cache_invalidate", lambda self, keys=(), patterns=(): False)

    response = client.post("/orders", json=order_body((ISBN_A, 1)), headers=user_headers)

    assert response.status_code == 201
    assert order_db.books[ISBN_A]["stock"] == 4
