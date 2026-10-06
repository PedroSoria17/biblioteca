"""
Request validation for /authors, based on the real table (01_schema.sql):

    autores (autor_id BIGSERIAL PK, nombre VARCHAR(120) NOT NULL,
             apellido VARCHAR(120) NOT NULL, pais VARCHAR(80) NULL)
    libro_autor (isbn, autor_id, orden SMALLINT NOT NULL DEFAULT 1,
                 PRIMARY KEY (isbn, autor_id))

autores has no timestamps and no UNIQUE constraint besides the PK.
"""

from __future__ import annotations

from typing import Any

from utils.errors import fields_not_allowed, invalid_body, invalid_input, unknown_fields


MAX_NOMBRE_LENGTH = 120
MAX_APELLIDO_LENGTH = 120
MAX_PAIS_LENGTH = 80
MAX_ISBN_LENGTH = 20  # libros.isbn VARCHAR(20)
MAX_ORDEN = 32767  # SMALLINT
MAX_Q_LENGTH = 120

EDITABLE_FIELDS = ("nombre", "apellido", "pais")
SERVER_MANAGED_FIELDS = ("autor_id",)
REQUIRED_FIELDS = ("nombre", "apellido")


def _check_keys(body: Any, allowed: tuple[str, ...], managed: tuple[str, ...]) -> dict:
    if not isinstance(body, dict):
        raise invalid_body()

    sent_managed = sorted(k for k in body if k in managed)
    if sent_managed:
        raise fields_not_allowed(sent_managed)

    unknown = sorted(k for k in body if k not in allowed)
    if unknown:
        raise unknown_fields(unknown)

    return body


def _required_text(name: str, value: Any, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_input(f"Field '{name}' must be a non-empty string.")
    value = value.strip()
    if len(value) > max_length:
        raise invalid_input(f"Field '{name}' must be at most {max_length} characters.")
    return value


def _pais(value: Any) -> str | None:
    # Nullable column: null clears it. A blank string is rejected instead of
    # being stored as '' (ambiguous with "unknown").
    if value is None:
        return None
    return _required_text("pais", value, MAX_PAIS_LENGTH)


_PARSERS = {
    "nombre": lambda v: _required_text("nombre", v, MAX_NOMBRE_LENGTH),
    "apellido": lambda v: _required_text("apellido", v, MAX_APELLIDO_LENGTH),
    "pais": _pais,
}


def _parse_present(body: dict) -> dict:
    return {name: _PARSERS[name](body[name]) for name in EDITABLE_FIELDS if name in body}


def parse_create(body: Any) -> dict:
    """POST: nombre and apellido required; pais optional (NULL if absent)."""
    body = _check_keys(body, EDITABLE_FIELDS, SERVER_MANAGED_FIELDS)
    missing = [name for name in REQUIRED_FIELDS if name not in body]
    if missing:
        raise invalid_input("Missing required fields: " + ", ".join(missing) + ".")
    values = _parse_present(body)
    values.setdefault("pais", None)
    return values


def parse_replace(body: Any) -> dict:
    """
    PUT: full representation. All three fields are required; pais may be
    null, but it must be sent explicitly so a PUT never clears it by
    accident.
    """
    body = _check_keys(body, EDITABLE_FIELDS, SERVER_MANAGED_FIELDS)
    missing = [name for name in EDITABLE_FIELDS if name not in body]
    if missing:
        raise invalid_input("Missing required fields: " + ", ".join(missing) + ".")
    return _parse_present(body)


def parse_patch(body: Any) -> dict:
    body = _check_keys(body, EDITABLE_FIELDS, SERVER_MANAGED_FIELDS)
    if not body:
        raise invalid_input("At least one field is required.")
    return _parse_present(body)


def parse_relation(body: Any) -> int | None:
    """
    Optional body of POST /authors/<id>/books/<isbn>: {"orden": n}.
    No body (or {}) -> None: the author is appended after the book's
    current authors.
    """
    if body is None:
        return None
    body = _check_keys(body, ("orden",), ("autor_id", "isbn"))
    if "orden" not in body:
        return None
    orden = body["orden"]
    if not isinstance(orden, int) or isinstance(orden, bool) or not 1 <= orden <= MAX_ORDEN:
        raise invalid_input(f"Field 'orden' must be an integer between 1 and {MAX_ORDEN}.")
    return orden


def normalize_isbn(raw: str) -> str:
    """Same rule as Books (catalog/validation.py): strip + uppercase 'x'."""
    return (raw or "").strip().upper()


def is_plausible_isbn(isbn: str) -> bool:
    # The CHECK on libros.isbn decides the real format; anything empty or
    # longer than the column can never match a row.
    return 0 < len(isbn) <= MAX_ISBN_LENGTH


def parse_list_args(args) -> tuple[int, int, str | None]:
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

    q = (args.get("q") or "").strip()
    if len(q) > MAX_Q_LENGTH:
        raise invalid_input(f"Query parameter 'q' must be at most {MAX_Q_LENGTH} characters.")
    return limit, offset, (q or None)
