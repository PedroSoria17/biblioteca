"""
Request validation for /orders, based on the real tables
(data/07_microservices_auth_orders_payments.sql):

    pedidos        (pedido_id, usuario_id, estado, total, fecha_creacion, fecha_actualizacion)
    pedido_detalle (pedido_id, isbn, cantidad, precio_unitario, subtotal GENERATED)

The client only chooses WHAT to buy (isbn + cantidad). Owner, prices,
subtotals, total, status and timestamps are decided by the server.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any

from services.status import STATUSES
from utils.errors import fields_not_allowed, invalid_body, invalid_input, unknown_fields


# Same pattern as the libros_isbn_check CHECK constraint (01_schema.sql).
ISBN_PATTERN = re.compile(r"^(97[89])?[0-9]{9}[0-9X]$|^(97[89]-)?[0-9]{1,5}-[0-9]{1,7}-[0-9]{1,7}-[0-9X]$")
MAX_ISBN_LENGTH = 20
MAX_ITEMS = 100  # entries in one request
MAX_CANTIDAD = 10_000  # per entry and per consolidated line

ORDER_FIELDS = ("items",)
ORDER_SERVER_FIELDS = ("pedido_id", "usuario_id", "estado", "status", "total", "fecha_creacion", "fecha_actualizacion")
ITEM_FIELDS = ("isbn", "cantidad")
ITEM_SERVER_FIELDS = ("pedido_id", "precio_unitario", "precio", "subtotal")


def _check_keys(body: Any, allowed: tuple[str, ...], managed: tuple[str, ...], where: str = "") -> dict:
    if not isinstance(body, dict):
        raise invalid_body() if not where else invalid_input(f"{where} must be a JSON object.")

    sent_managed = sorted(k for k in body if k in managed)
    if sent_managed:
        raise fields_not_allowed([f"{where}.{k}" if where else k for k in sent_managed])

    unknown = sorted(k for k in body if k not in allowed)
    if unknown:
        raise unknown_fields([f"{where}.{k}" if where else k for k in unknown])

    return body


def normalize_isbn(raw: str) -> str:
    """Same rule as Books (catalog/validation.py): strip + uppercase 'x'."""
    return raw.strip().upper()


def _isbn(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid_input(f"{where}.isbn must be a non-empty string.")
    isbn = normalize_isbn(value)
    if len(isbn) > MAX_ISBN_LENGTH or not ISBN_PATTERN.match(isbn):
        raise invalid_input(f"{where}.isbn must be a valid ISBN-10 or ISBN-13.")
    return isbn


def _cantidad(value: Any, where: str) -> int:
    # bool is an int subclass: true must not become 1. 2.0 / "2" are rejected.
    if not isinstance(value, int) or isinstance(value, bool):
        raise invalid_input(f"{where}.cantidad must be an integer.")
    if not 1 <= value <= MAX_CANTIDAD:
        raise invalid_input(f"{where}.cantidad must be between 1 and {MAX_CANTIDAD}.")
    return value


def parse_create_order(body: Any) -> dict[str, int]:
    """
    Returns {isbn: cantidad} sorted by ISBN. Repeated ISBNs are CONSOLIDATED
    (2 + 3 -> one line with 5): pedido_detalle has PRIMARY KEY
    (pedido_id, isbn), so one book is one line per order.
    """
    body = _check_keys(body, ORDER_FIELDS, ORDER_SERVER_FIELDS)
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise invalid_input("Field 'items' must be a non-empty list.")
    if len(items) > MAX_ITEMS:
        raise invalid_input(f"Field 'items' accepts at most {MAX_ITEMS} entries.")

    lines: dict[str, int] = {}
    for index, item in enumerate(items):
        where = f"items[{index}]"
        item = _check_keys(item, ITEM_FIELDS, ITEM_SERVER_FIELDS, where)
        missing = [f for f in ITEM_FIELDS if f not in item]
        if missing:
            raise invalid_input(f"{where} is missing: {', '.join(missing)}.")
        isbn = _isbn(item["isbn"], where)
        lines[isbn] = lines.get(isbn, 0) + _cantidad(item["cantidad"], where)

    for isbn, cantidad in lines.items():
        if cantidad > MAX_CANTIDAD:
            raise invalid_input(f"Total cantidad for {isbn} must be at most {MAX_CANTIDAD}.")

    return dict(sorted(lines.items()))


def parse_status(body: Any) -> str:
    body = _check_keys(body, ("estado",), ())
    estado = body.get("estado")
    if not isinstance(estado, str) or estado.strip().lower() not in STATUSES:
        raise invalid_input("Field 'estado' must be one of: " + ", ".join(STATUSES) + ".")
    return estado.strip().lower()


# ---------------------------------------------------------------------------
# Query strings
# ---------------------------------------------------------------------------

def _int_arg(args, name: str, default: int | None, minimum: int, maximum: int | None) -> int | None:
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


def _estado_arg(args) -> str | None:
    raw = (args.get("estado") or "").strip().lower()
    if not raw:
        return None
    if raw not in STATUSES:
        raise invalid_input("Query parameter 'estado' must be one of: " + ", ".join(STATUSES) + ".")
    return raw


def _datetime_arg(args, name: str, end_of_day: bool) -> datetime | None:
    """
    ISO 8601 date or datetime. A bare date for `hasta` covers that whole
    day. Datetimes without offset are taken as UTC.
    """
    raw = (args.get(name) or "").strip()
    if not raw:
        return None
    try:
        if len(raw) == 10:
            day = date.fromisoformat(raw)
            value = datetime.combine(day + timedelta(days=1) if end_of_day else day, time.min)
        else:
            value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise invalid_input(f"Query parameter '{name}' must be an ISO 8601 date or datetime.") from exc
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def parse_pagination(args) -> tuple[int, int]:
    return _int_arg(args, "limit", 50, 1, 200), _int_arg(args, "offset", 0, 0, None)


def parse_admin_filters(args) -> dict[str, Any]:
    """GET /orders (ADMIN): estado, usuario_id, desde (inclusive), hasta (exclusive)."""
    filters = {
        "estado": _estado_arg(args),
        "usuario_id": _int_arg(args, "usuario_id", None, 1, 9223372036854775807),
        "desde": _datetime_arg(args, "desde", end_of_day=False),
        "hasta": _datetime_arg(args, "hasta", end_of_day=True),
    }
    if filters["desde"] and filters["hasta"] and filters["desde"] >= filters["hasta"]:
        raise invalid_input("'desde' must be earlier than 'hasta'.")
    return filters


def parse_own_filters(args) -> dict[str, Any]:
    """GET /orders/me: only estado. The owner always comes from the token."""
    if "usuario_id" in args:
        raise invalid_input("Query parameter 'usuario_id' is not accepted here; the user comes from the token.")
    return {"estado": _estado_arg(args), "usuario_id": None, "desde": None, "hasta": None}
