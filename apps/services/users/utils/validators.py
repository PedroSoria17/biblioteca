"""
Request-body validation for POST/PUT/PATCH /users.

Email and password rules are the SAME ones Login applies in /register
(apps/services/login/utils/validators.py): strip + lowercase emails, the
same structural regex, and at least 8 characters for passwords. Otherwise a
user created here could be unreachable from /login (e.g. an email stored
with uppercase letters, which Login would never match).
"""

from __future__ import annotations

import re
from typing import Any

from utils.errors import fields_not_allowed, invalid_body, invalid_input, unknown_fields


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8
# bcrypt only uses the first 72 bytes of the password. Longer passwords are
# rejected instead of being silently truncated.
MAX_PASSWORD_BYTES = 72
MAX_NOMBRE_LENGTH = 150  # usuarios.nombre_completo VARCHAR(150)
MAX_EMAIL_LENGTH = 255  # usuarios.email VARCHAR(255)

EDITABLE_FIELDS = ("nombre_completo", "email", "password", "role_id", "activo")
# Columns that exist in usuarios but are derived/managed by the server or
# the database (trigger, defaults, BIGSERIAL). Sending them is an error,
# not something to ignore silently.
SERVER_MANAGED_FIELDS = ("usuario_id", "password_hash", "es_administrador", "fecha_registro")

POST_REQUIRED = ("nombre_completo", "email", "password")
PUT_REQUIRED = ("nombre_completo", "email", "role_id", "activo")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _check_keys(body: Any) -> dict:
    if not isinstance(body, dict):
        raise invalid_body()

    managed = sorted(k for k in body if k in SERVER_MANAGED_FIELDS)
    if managed:
        raise fields_not_allowed(managed)

    unknown = sorted(k for k in body if k not in EDITABLE_FIELDS)
    if unknown:
        raise unknown_fields(unknown)

    return body


def _nombre(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_input("Field 'nombre_completo' must be a non-empty string.")
    value = value.strip()
    if len(value) > MAX_NOMBRE_LENGTH:
        raise invalid_input(f"Field 'nombre_completo' must be at most {MAX_NOMBRE_LENGTH} characters.")
    return value


def _email(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_input("Field 'email' must be a non-empty string.")
    value = normalize_email(value)
    if len(value) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(value):
        raise invalid_input("Field 'email' has an invalid format.")
    return value


def _password(value: Any) -> str:
    # Never echo the value back in the error message.
    if not isinstance(value, str) or len(value) < MIN_PASSWORD_LENGTH:
        raise invalid_input(f"Field 'password' must be a string of at least {MIN_PASSWORD_LENGTH} characters.")
    if not value.strip():
        raise invalid_input("Field 'password' cannot be blank.")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise invalid_input(f"Field 'password' must be at most {MAX_PASSWORD_BYTES} bytes.")
    return value


def _role_id(value: Any) -> int:
    # bool is a subclass of int: true must not become role_id = 1.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise invalid_input("Field 'role_id' must be a positive integer.")
    return value


def _activo(value: Any) -> bool:
    if not isinstance(value, bool):
        raise invalid_input("Field 'activo' must be a boolean.")
    return value


_PARSERS = {
    "nombre_completo": _nombre,
    "email": _email,
    "password": _password,
    "role_id": _role_id,
    "activo": _activo,
}


def _parse_present(body: dict) -> dict:
    return {name: _PARSERS[name](body[name]) for name in EDITABLE_FIELDS if name in body}


def _require(body: dict, required: tuple[str, ...]) -> None:
    missing = [name for name in required if name not in body]
    if missing:
        raise invalid_input("Missing required fields: " + ", ".join(missing) + ".")


def parse_create(body: Any) -> dict:
    """POST: role_id defaults to USER (1) and activo to true."""
    body = _check_keys(body)
    _require(body, POST_REQUIRED)
    values = _parse_present(body)
    values.setdefault("role_id", 1)
    values.setdefault("activo", True)
    return values


def parse_replace(body: Any) -> dict:
    """
    PUT: every administrative field is required except `password`. The
    password is a credential, not part of the user's representation (it is
    never returned), so omitting it keeps the current hash; sending it
    replaces the hash.
    """
    body = _check_keys(body)
    _require(body, PUT_REQUIRED)
    return _parse_present(body)


def parse_patch(body: Any) -> dict:
    """PATCH: only the fields present are changed; at least one is required."""
    body = _check_keys(body)
    if not body:
        raise invalid_input("At least one field is required.")
    return _parse_present(body)


def parse_pagination(args) -> tuple[int, int]:
    def _int_arg(name: str, default: int, minimum: int, maximum: int | None) -> int:
        raw = args.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise invalid_input(f"Query parameter '{name}' must be an integer.") from exc
        if value < minimum or (maximum is not None and value > maximum):
            limit_text = f" and {maximum}" if maximum is not None else ""
            raise invalid_input(f"Query parameter '{name}' must be between {minimum}{limit_text}.")
        return value

    limit = _int_arg("limit", 50, 1, 200)
    offset = _int_arg("offset", 0, 0, None)
    return limit, offset
