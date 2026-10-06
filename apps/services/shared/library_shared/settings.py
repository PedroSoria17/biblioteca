"""
Environment-driven configuration shared by every microservice.

Each loader only reads the variables its feature needs, so a service that
only uses the Redis cache does not have to define JWT_SECRET_KEY and vice
versa. Nothing here calls load_dotenv(): each service already loads its own
.env in its config module before these loaders run.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from library_shared.errors import ConfigurationError
from library_shared.redaction import redact_url


# HS256 needs a key of at least 256 bits; anything shorter is rejected at
# startup instead of silently producing weak signatures.
MIN_JWT_SECRET_LENGTH = 32

DEFAULT_ACCESS_TTL_MINUTES = 20
DEFAULT_REFRESH_TTL_DAYS = 7
DEFAULT_BOOKS_CACHE_TTL_SECONDS = 60
DEFAULT_REDIS_CONNECT_TIMEOUT_SECONDS = 2.0
DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS = 2.0
DEFAULT_REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 30

PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value.strip()


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def app_environment(env: Mapping[str, str] | None = None) -> str:
    """APP_ENV wins; FLASK_ENV is accepted because login already uses it."""
    env = _env(env)
    return (env.get("APP_ENV") or env.get("FLASK_ENV") or "development").strip().lower()


@dataclass(frozen=True)
class JwtSettings:
    secret_key: str
    access_ttl_seconds: int
    refresh_ttl_seconds: int

    def __repr__(self) -> str:
        # Never let the secret end up in a log line or traceback.
        return (
            "JwtSettings(secret_key='***', "
            f"access_ttl_seconds={self.access_ttl_seconds}, "
            f"refresh_ttl_seconds={self.refresh_ttl_seconds})"
        )


def load_jwt_settings(env: Mapping[str, str] | None = None) -> JwtSettings:
    env = _env(env)
    secret = _required(env, "JWT_SECRET_KEY")
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise ConfigurationError(
            f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters long."
        )

    access_minutes = _positive_int(env, "JWT_ACCESS_TTL_MINUTES", DEFAULT_ACCESS_TTL_MINUTES)
    refresh_days = _positive_int(env, "JWT_REFRESH_TTL_DAYS", DEFAULT_REFRESH_TTL_DAYS)

    access_ttl = access_minutes * 60
    refresh_ttl = refresh_days * 24 * 60 * 60
    if refresh_ttl <= access_ttl:
        raise ConfigurationError("JWT_REFRESH_TTL_DAYS must produce a longer lifetime than the access token.")

    return JwtSettings(
        secret_key=secret,
        access_ttl_seconds=access_ttl,
        refresh_ttl_seconds=refresh_ttl,
    )


@dataclass(frozen=True)
class RedisSettings:
    url: str
    connect_timeout_seconds: float
    socket_timeout_seconds: float
    health_check_interval_seconds: int

    def __repr__(self) -> str:
        return (
            f"RedisSettings(url='{redact_url(self.url)}', "
            f"connect_timeout_seconds={self.connect_timeout_seconds}, "
            f"socket_timeout_seconds={self.socket_timeout_seconds}, "
            f"health_check_interval_seconds={self.health_check_interval_seconds})"
        )


def load_redis_settings(env: Mapping[str, str] | None = None) -> RedisSettings:
    env = _env(env)
    url = _required(env, "REDIS_URL")
    if not url.startswith(("redis://", "rediss://", "unix://")):
        raise ConfigurationError("REDIS_URL must start with redis://, rediss:// or unix://.")

    return RedisSettings(
        url=url,
        connect_timeout_seconds=_positive_float(
            env, "REDIS_CONNECT_TIMEOUT_SECONDS", DEFAULT_REDIS_CONNECT_TIMEOUT_SECONDS
        ),
        socket_timeout_seconds=_positive_float(
            env, "REDIS_SOCKET_TIMEOUT_SECONDS", DEFAULT_REDIS_SOCKET_TIMEOUT_SECONDS
        ),
        health_check_interval_seconds=_positive_int(
            env, "REDIS_HEALTH_CHECK_INTERVAL_SECONDS", DEFAULT_REDIS_HEALTH_CHECK_INTERVAL_SECONDS
        ),
    )


def load_books_cache_ttl(env: Mapping[str, str] | None = None) -> int:
    return _positive_int(_env(env), "BOOKS_CACHE_TTL_SECONDS", DEFAULT_BOOKS_CACHE_TTL_SECONDS)


@dataclass(frozen=True)
class CorsSettings:
    allowed_origins: tuple[str, ...]


def load_cors_settings(env: Mapping[str, str] | None = None) -> CorsSettings:
    """
    CORS_ALLOWED_ORIGINS is a comma-separated list of exact origins
    (scheme://host[:port]). Empty means "no cross-origin access at all".
    '*' is only tolerated outside production.
    """
    env = _env(env)
    raw = env.get("CORS_ALLOWED_ORIGINS") or ""
    origins = tuple(dict.fromkeys(o.strip().rstrip("/") for o in raw.split(",") if o.strip()))

    if "*" in origins:
        if app_environment(env) in PRODUCTION_ENVIRONMENTS:
            raise ConfigurationError("CORS_ALLOWED_ORIGINS cannot contain '*' in production.")
        if len(origins) > 1:
            raise ConfigurationError("CORS_ALLOWED_ORIGINS cannot mix '*' with explicit origins.")
        return CorsSettings(allowed_origins=origins)

    for origin in origins:
        if not origin.startswith(("http://", "https://")):
            raise ConfigurationError(f"Invalid origin in CORS_ALLOWED_ORIGINS: {origin}")

    return CorsSettings(allowed_origins=origins)
