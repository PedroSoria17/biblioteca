from __future__ import annotations

import pytest

from conftest import DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD


def _assert_no_secrets(text: str) -> None:
    for secret in (DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD):
        assert secret not in text


def test_health_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "service": "users",
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }


def test_health_reports_redis_down_as_unhealthy(client, fake_redis):
    fake_redis.down = True

    response = client.get("/health")

    assert response.status_code == 503
    body = response.get_json()
    assert body["redis"] == "unavailable"
    assert body["database"] == "connected"
    assert body["status"] == "unhealthy"
    _assert_no_secrets(response.get_data(as_text=True))


def test_health_reports_database_down(client, user_db):
    user_db.down = True

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["database"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_cors_allows_configured_origin_only(client):
    allowed = client.options(
        "/users",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    denied = client.options(
        "/users",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )

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


def test_short_jwt_secret_is_rejected(env, monkeypatch, gateway):
    from app import create_app
    from config import ConfigurationError

    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")

    with pytest.raises(ConfigurationError):
        create_app(redis_gateway=gateway)


def test_default_port_is_5002(env, monkeypatch):
    from config import get_settings

    monkeypatch.delenv("FLASK_PORT", raising=False)

    settings = get_settings()
    assert settings.flask_port == 5002
    assert DB_PASSWORD not in repr(settings)
