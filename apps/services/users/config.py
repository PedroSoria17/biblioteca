from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv
from library_shared.errors import ConfigurationError as SharedConfigurationError
from library_shared.settings import (
    CorsSettings,
    JwtSettings,
    RedisSettings,
    load_cors_settings,
    load_jwt_settings,
    load_redis_settings,
)


load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value.strip()


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc


@dataclass(frozen=True)
class Settings:
    flask_host: str
    flask_port: int
    flask_debug: bool

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    def __repr__(self) -> str:
        # Never let the database password end up in a log line or traceback.
        return (
            f"Settings(flask_host={self.flask_host!r}, flask_port={self.flask_port}, "
            f"flask_debug={self.flask_debug}, db_host={self.db_host!r}, db_port={self.db_port}, "
            f"db_name={self.db_name!r}, db_user={self.db_user!r}, db_password='***')"
        )


def get_settings() -> Settings:
    return Settings(
        flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
        flask_port=_int("FLASK_PORT", "5002"),
        flask_debug=_bool("FLASK_DEBUG", "false"),
        db_host=_required("DB_HOST"),
        db_port=_int("DB_PORT", "5432"),
        db_name=_required("DB_NAME"),
        db_user=_required("DB_USER"),
        db_password=_required("DB_PASSWORD"),
    )


@dataclass(frozen=True)
class SecuritySettings:
    jwt: JwtSettings
    redis: RedisSettings
    cors: CorsSettings


def get_security_settings() -> SecuritySettings:
    """
    JWT/Redis/CORS configuration, read and validated by library_shared
    (apps/services/shared). JWT_SECRET_KEY and REDIS_URL are mandatory:
    every endpoint except /health is protected, and protected endpoints
    need Redis to check JWT revocation.
    """
    try:
        return SecuritySettings(
            jwt=load_jwt_settings(),
            redis=load_redis_settings(),
            cors=load_cors_settings(),
        )
    except SharedConfigurationError as exc:
        raise ConfigurationError(str(exc)) from exc
