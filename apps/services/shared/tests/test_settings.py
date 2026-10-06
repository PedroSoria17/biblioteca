import pytest

from library_shared.errors import ConfigurationError
from library_shared.settings import (
    load_books_cache_ttl,
    load_cors_settings,
    load_jwt_settings,
    load_redis_settings,
)


SECRET = "s" * 40


def test_jwt_defaults_access_20_minutes():
    settings = load_jwt_settings({"JWT_SECRET_KEY": SECRET})

    assert settings.access_ttl_seconds == 20 * 60
    assert settings.refresh_ttl_seconds == 7 * 24 * 3600


def test_jwt_settings_repr_hides_secret():
    assert SECRET not in repr(load_jwt_settings({"JWT_SECRET_KEY": SECRET}))


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"JWT_SECRET_KEY": "   "},
        {"JWT_SECRET_KEY": "short"},
        {"JWT_SECRET_KEY": SECRET, "JWT_ACCESS_TTL_MINUTES": "abc"},
        {"JWT_SECRET_KEY": SECRET, "JWT_ACCESS_TTL_MINUTES": "0"},
        {"JWT_SECRET_KEY": SECRET, "JWT_ACCESS_TTL_MINUTES": "20000", "JWT_REFRESH_TTL_DAYS": "1"},
    ],
)
def test_invalid_jwt_configuration_fails_fast(env):
    with pytest.raises(ConfigurationError):
        load_jwt_settings(env)


def test_redis_settings_from_env():
    settings = load_redis_settings(
        {"REDIS_URL": "redis://:pw@10.0.0.5:6379/0", "REDIS_SOCKET_TIMEOUT_SECONDS": "1.5"}
    )

    assert settings.socket_timeout_seconds == 1.5
    assert settings.connect_timeout_seconds == 2.0
    assert "pw" not in repr(settings)


@pytest.mark.parametrize("env", [{}, {"REDIS_URL": "http://host"}, {"REDIS_URL": "redis://h", "REDIS_CONNECT_TIMEOUT_SECONDS": "-1"}])
def test_invalid_redis_configuration_fails_fast(env):
    with pytest.raises(ConfigurationError):
        load_redis_settings(env)


def test_books_cache_ttl():
    assert load_books_cache_ttl({}) == 60
    assert load_books_cache_ttl({"BOOKS_CACHE_TTL_SECONDS": "15"}) == 15


def test_cors_explicit_origins_are_normalized():
    settings = load_cors_settings(
        {"CORS_ALLOWED_ORIGINS": "http://localhost:3000/, http://127.0.0.1:5173,http://localhost:3000"}
    )

    assert settings.allowed_origins == ("http://localhost:3000", "http://127.0.0.1:5173")


def test_cors_empty_means_no_origins():
    assert load_cors_settings({}).allowed_origins == ()


def test_cors_wildcard_rejected_in_production():
    with pytest.raises(ConfigurationError):
        load_cors_settings({"CORS_ALLOWED_ORIGINS": "*", "APP_ENV": "production"})


def test_cors_wildcard_allowed_only_in_development():
    assert load_cors_settings({"CORS_ALLOWED_ORIGINS": "*", "FLASK_ENV": "development"}).allowed_origins == ("*",)


def test_cors_rejects_invalid_origin():
    with pytest.raises(ConfigurationError):
        load_cors_settings({"CORS_ALLOWED_ORIGINS": "localhost:3000"})
