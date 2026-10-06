"""
Server-side validation of POST/PUT/PATCH /books bodies.

Mirrors the real `libros` table (data/01_schema.sql) so PostgreSQL never
has to be the one rejecting malformed input:

    isbn              VARCHAR(20) PK, CHECK (ISBN-10/13, optionally hyphenated)
    titulo            VARCHAR(300) NOT NULL
    anio_publicacion  SMALLINT NOT NULL CHECK (1450..2100)
    precio            NUMERIC(10,2) NOT NULL CHECK (>= 0)
    stock             INTEGER NOT NULL DEFAULT 0 CHECK (>= 0)
    formato_id        SMALLINT NOT NULL FK formatos
    categoria_id      SMALLINT NOT NULL FK categorias

fecha_creacion / fecha_actualizacion are managed by PostgreSQL and are not
accepted from the client.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from catalog.errors import invalid_input


# Same expression as the CHECK constraint on libros.isbn.
ISBN_PATTERN = re.compile(
    r"^(97[89])?[0-9]{9}[0-9X]$|^(97[89]-)?[0-9]{1,5}-[0-9]{1,7}-[0-9]{1,7}-[0-9X]$"
)
ISBN_MAX_LENGTH = 20
TITULO_MAX_LENGTH = 300
MIN_YEAR, MAX_YEAR = 1450, 2100
MAX_PRICE = Decimal("99999999.99")   # NUMERIC(10,2)
MAX_INTEGER = 2_147_483_647          # INTEGER
MAX_SMALLINT = 32_767                # SMALLINT

MUTABLE_FIELDS = ("titulo", "anio_publicacion", "precio", "stock", "formato_id", "categoria_id")
REQUIRED_ON_CREATE = ("titulo", "anio_publicacion", "precio", "formato_id", "categoria_id")


def normalize_isbn(raw: Any) -> str:
    """
    Coherent with how PostgreSQL stores it: surrounding spaces removed and a
    lowercase check digit 'x' upper-cased (the CHECK only accepts 'X').
    Hyphens are kept: "978-..." and "978..." are different primary keys.
    """
    return str(raw or "").strip().upper()


def is_valid_isbn(isbn: str) -> bool:
    return len(isbn) <= ISBN_MAX_LENGTH and bool(ISBN_PATTERN.match(isbn))


def _int(field: str, value: Any, minimum: int, maximum: int) -> int:
    # bool is an int subclass: `true` must not become 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid_input(f"Field '{field}' must be an integer.")
    if not minimum <= value <= maximum:
        raise invalid_input(f"Field '{field}' must be between {minimum} and {maximum}.")
    return value


def _titulo(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_input("Field 'titulo' must be a non-empty string.")
    value = value.strip()
    if len(value) > TITULO_MAX_LENGTH:
        raise invalid_input(f"Field 'titulo' must be at most {TITULO_MAX_LENGTH} characters.")
    return value


def _precio(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise invalid_input("Field 'precio' must be a number.")
    try:
        # str() first so 19.9 becomes Decimal("19.9"), not a binary float.
        price = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise invalid_input("Field 'precio' must be a number.") from exc
    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        raise invalid_input(f"Field 'precio' must be between 0 and {MAX_PRICE}.")
    if price.as_tuple().exponent < -2:
        raise invalid_input("Field 'precio' must have at most 2 decimal places.")
    return price


VALIDATORS = {
    "titulo": _titulo,
    "anio_publicacion": lambda v: _int("anio_publicacion", v, MIN_YEAR, MAX_YEAR),
    "precio": _precio,
    "stock": lambda v: _int("stock", v, 0, MAX_INTEGER),
    "formato_id": lambda v: _int("formato_id", v, 1, MAX_SMALLINT),
    "categoria_id": lambda v: _int("categoria_id", v, 1, MAX_SMALLINT),
}


def _require_object(body: Any) -> dict:
    if not isinstance(body, dict):
        raise invalid_input("Request body must be a JSON object.")
    return body


def _validate_fields(body: dict, allowed: set[str]) -> dict[str, Any]:
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise invalid_input(f"Unknown field(s): {', '.join(unknown)}.")

    values: dict[str, Any] = {}
    for field in MUTABLE_FIELDS:
        if field in body:
            if body[field] is None:
                raise invalid_input(f"Field '{field}' cannot be null.")
            values[field] = VALIDATORS[field](body[field])
    return values


def _check_body_isbn(body: dict, path_isbn: str) -> None:
    if "isbn" in body and normalize_isbn(body["isbn"]) != path_isbn:
        raise invalid_input("The ISBN cannot be changed; it must match the URL.")


def validate_create(body: Any) -> tuple[str, dict[str, Any]]:
    body = _require_object(body)

    isbn = normalize_isbn(body.get("isbn"))
    if not isbn:
        raise invalid_input("Field 'isbn' is required.")
    if not is_valid_isbn(isbn):
        raise invalid_input("Field 'isbn' must be a valid ISBN-10 or ISBN-13.")

    values = _validate_fields(body, {"isbn", *MUTABLE_FIELDS})
    missing = [f for f in REQUIRED_ON_CREATE if f not in values]
    if missing:
        raise invalid_input(f"Missing required field(s): {', '.join(missing)}.")
    values.setdefault("stock", 0)  # same DEFAULT as the table
    return isbn, values


def validate_replace(body: Any, path_isbn: str) -> dict[str, Any]:
    """PUT: full representation of every mutable field (stock included)."""
    body = _require_object(body)
    _check_body_isbn(body, path_isbn)

    values = _validate_fields(body, {"isbn", *MUTABLE_FIELDS})
    missing = [f for f in MUTABLE_FIELDS if f not in values]
    if missing:
        raise invalid_input(f"PUT requires every field; missing: {', '.join(missing)}.")
    return values


def validate_patch(body: Any, path_isbn: str) -> dict[str, Any]:
    """PATCH: only the fields present are validated and updated."""
    body = _require_object(body)
    _check_body_isbn(body, path_isbn)

    values = _validate_fields(body, {"isbn", *MUTABLE_FIELDS})
    if not values:
        raise invalid_input(f"PATCH requires at least one of: {', '.join(MUTABLE_FIELDS)}.")
    return values
