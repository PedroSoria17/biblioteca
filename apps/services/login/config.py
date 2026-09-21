from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


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
    flask_env: str
    flask_host: str
    flask_port: int
    flask_debug: bool
    secret_key: str
    session_cookie_secure: bool

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    mail_enabled: bool
    mail_host: str
    mail_port: int
    mail_username: str | None
    mail_password: str | None
    mail_use_tls: bool
    mail_from: str

    public_base_url: str
    email_token_expiration_minutes: int

    dev_show_verification_link: bool


def get_settings() -> Settings:
    return Settings(
        flask_env=os.getenv("FLASK_ENV", "development"),
        flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
        flask_port=_int("FLASK_PORT", "5001"),
        flask_debug=_bool("FLASK_DEBUG", "false"),
        secret_key=_required("SECRET_KEY"),
        session_cookie_secure=_bool("SESSION_COOKIE_SECURE", "false"),
        db_host=_required("DB_HOST"),
        db_port=_int("DB_PORT", "5432"),
        db_name=_required("DB_NAME"),
        db_user=_required("DB_USER"),
        db_password=_required("DB_PASSWORD"),
        mail_enabled=_bool("MAIL_ENABLED", "false"),
        mail_host=os.getenv("MAIL_HOST", "localhost"),
        mail_port=_int("MAIL_PORT", "25"),
        mail_username=os.getenv("MAIL_USERNAME") or None,
        mail_password=os.getenv("MAIL_PASSWORD") or None,
        mail_use_tls=_bool("MAIL_USE_TLS", "false"),
        mail_from=os.getenv("MAIL_FROM", "no-reply@localhost"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5001").rstrip("/"),
        email_token_expiration_minutes=_int("EMAIL_TOKEN_EXPIRATION_MINUTES", "60"),
        dev_show_verification_link=_bool("DEV_SHOW_VERIFICATION_LINK", "false"),
    )
