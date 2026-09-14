from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ConfigurationError(
            f"Missing required environment variable: {name}"
        )
    return value.strip()


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    flask_host: str
    flask_port: int
    flask_debug: bool


def get_settings() -> Settings:
    try:
        pg_port = int(os.getenv("PGPORT", "5432"))
        flask_port = int(os.getenv("FLASK_PORT", "5000"))
    except ValueError as exc:
        raise ConfigurationError(
            "PGPORT and FLASK_PORT must be integers."
        ) from exc

    return Settings(
        pg_host=_required("PGHOST"),
        pg_port=pg_port,
        pg_database=_required("PGDATABASE"),
        pg_user=_required("PGUSER"),
        pg_password=_required("PGPASSWORD"),
        flask_host=os.getenv("FLASK_HOST", "127.0.0.1"),
        flask_port=flask_port,
        flask_debug=os.getenv("FLASK_DEBUG", "false").lower()
        in {"1", "true", "yes", "on"},
    )
