from __future__ import annotations

import pytest

from conftest import DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD


def _assert_no_secrets(text: str) -> None:
    for secret in (DB_PASSWORD, JWT_SECRET, REDIS_PASSWORD):
        assert secret not in text


def test_health_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "service": "authors",
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
        "public_reads": "available",
        "writes": "available",
    }


def test_health_degraded_when_redis_is_down(client, fake_redis):
    fake_redis.down = True

    response = client.get("/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "degraded"
    assert body["success"] is False
    assert body["redis"] == "unavailable"
    assert body["public_reads"] == "available"
    assert body["writes"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_health_unavailable_when_database_is_down(client, author_db):
    author_db.down = True

    response = client.get("/health")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unavailable"
    assert body["public_reads"] == "unavailable"
    _assert_no_secrets(response.get_data(as_text=True))


def test_cors_allows_configured_origin_only(client):
    allowed = client.options(
        "/authors", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    denied = client.options(
        "/authors", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
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


def test_default_port_is_5003(env, monkeypatch):
    from config import get_settings

    monkeypatch.delenv("FLASK_PORT", raising=False)

    settings = get_settings()
    assert settings.flask_port == 5003
    assert DB_PASSWORD not in repr(settings)


def test_writes_are_logged_without_tokens(client, admin_headers, caplog):
    caplog.set_level("INFO")

    client.post("/authors", json={"nombre": "Log", "apellido": "Test"}, headers=admin_headers)

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Author 4 created by admin 1" in logged
    assert admin_headers["Authorization"].split()[1] not in logged
