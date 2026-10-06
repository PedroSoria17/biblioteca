"""
Central configuration of the desktop client: the base URL of every
microservice and the HTTP timeouts. Nothing else in the client hardcodes a
host or port.

Sources, in priority order:
  1. environment variables (e.g. set in the PowerShell session);
  2. desktop_client/.env (KEY=VALUE lines, optional, git-ignored);
  3. the local development defaults below.

Only URLs and timeouts live here; the client never stores credentials or
tokens in files.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


SERVICES = ("books", "login", "users", "authors", "orders", "payments")

DEFAULTS = {
    "BOOKS_BASE_URL": "http://127.0.0.1:5000",
    "LOGIN_BASE_URL": "http://127.0.0.1:5001",
    "USERS_BASE_URL": "http://127.0.0.1:5002",
    "AUTHORS_BASE_URL": "http://127.0.0.1:5003",
    "ORDERS_BASE_URL": "http://127.0.0.1:5004",
    "PAYMENTS_BASE_URL": "http://127.0.0.1:5005",
    "HTTP_TIMEOUT_SECONDS": "10",
    "HEALTH_TIMEOUT_SECONDS": "3",
    "HEALTH_REFRESH_SECONDS": "60",
}

ENV_FILE = Path(__file__).with_name(".env")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ClientConfig:
    base_urls: dict[str, str]
    http_timeout: float
    health_timeout: float
    health_refresh_seconds: int

    def url(self, service: str) -> str:
        return self.base_urls[service]

    @property
    def soap_endpoint(self) -> str:
        # SOAP keeps living in the Books service (port 5000).
        return self.base_urls["books"] + "/soap"


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser (comments and blank lines ignored)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _number(values: Mapping[str, str], name: str, cast):
    try:
        value = cast(values[name])
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero.")
    return value


def load_config(env: Mapping[str, str] | None = None, env_file: Path | None = ENV_FILE) -> ClientConfig:
    values = dict(DEFAULTS)
    if env_file is not None:
        values.update(read_env_file(env_file))
    environment = os.environ if env is None else env
    values.update({k: v for k, v in environment.items() if k in DEFAULTS and v})

    base_urls = {}
    for service in SERVICES:
        name = f"{service.upper()}_BASE_URL"
        url = values[name].strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"{name} must start with http:// or https://")
        base_urls[service] = url

    return ClientConfig(
        base_urls=base_urls,
        http_timeout=_number(values, "HTTP_TIMEOUT_SECONDS", float),
        health_timeout=_number(values, "HEALTH_TIMEOUT_SECONDS", float),
        health_refresh_seconds=_number(values, "HEALTH_REFRESH_SECONDS", int),
    )
