"""
Request validation for Payments, based on the real table:

    pagos (pago_id BIGSERIAL, pedido_id, monto NUMERIC(12,2) > 0,
           metodo_pago IN (credit_card, debit_card, bank_transfer, cash),
           estado DEFAULT 'pending', referencia VARCHAR(100) UNIQUE,
           fecha_pago, fecha_creacion, fecha_actualizacion)

The client chooses only WHICH order, HOW it pays and, optionally, the
external referencia (e.g. the bank transfer number). The amount is always
pedidos.total; the status, dates and ids are the server's.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any

from services.status import PAYMENT_METHODS, PAYMENT_STATUSES
from utils.errors import fields_not_allowed, invalid_body, invalid_input, unknown_fields


MAX_BIGINT = 9223372036854775807
MAX_REFERENCIA = 100  # pagos.referencia VARCHAR(100)
# Printable identifier: letters, digits and . _ : / - (no spaces/control chars).
REFERENCIA_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")

PAYMENT_FIELDS = ("pedido_id", "metodo_pago", "referencia")
PAYMENT_SERVER_FIELDS = (
    "pago_id", "monto", "estado", "status", "usuario_id",
    "fecha_pago", "fecha_creacion", "fecha_actualizacion",
)


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


def parse_create_payment(body: Any) -> dict[str, Any]:
    body = _check_keys(body, PAYMENT_FIELDS, PAYMENT_SERVER_FIELDS)

    pedido_id = body.get("pedido_id")
    if not isinstance(pedido_id, int) or isinstance(pedido_id, bool) or not 1 <= pedido_id <= MAX_BIGINT:
        raise invalid_input("Field 'pedido_id' must be a positive integer.")

    metodo = body.get("metodo_pago")
    if not isinstance(metodo, str) or metodo.strip().lower() not in PAYMENT_METHODS:
        raise invalid_input("Field 'metodo_pago' must be one of: " + ", ".join(PAYMENT_METHODS) + ".")

    referencia = body.get("referencia")
    if referencia is not None:
        if not isinstance(referencia, str) or not referencia.strip():
            raise invalid_input("Field 'referencia' must be a non-empty string.")
        referencia = referencia.strip()
        if len(referencia) > MAX_REFERENCIA or not REFERENCIA_PATTERN.match(referencia):
            raise invalid_input(
                f"Field 'referencia' must be at most {MAX_REFERENCIA} characters: letters, digits and . _ : / -"
            )

    return {"pedido_id": pedido_id, "metodo_pago": metodo.strip().lower(), "referencia": referencia}


def parse_empty_body(body: Any, has_data: bool) -> None:
    """approve / reject / refund take no body; {} is tolerated."""
    if not has_data:
        return
    _check_keys(body, (), PAYMENT_SERVER_FIELDS)


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


def _choice_arg(args, name: str, choices: tuple[str, ...]) -> str | None:
    raw = (args.get(name) or "").strip().lower()
    if not raw:
        return None
    if raw not in choices:
        raise invalid_input(f"Query parameter '{name}' must be one of: " + ", ".join(choices) + ".")
    return raw


def _datetime_arg(args, name: str, end_of_day: bool) -> datetime | None:
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


def parse_filters(args) -> dict[str, Any]:
    """
    ADMIN (GET /payments): pedido_id, estado, metodo_pago, desde (incl.),
    hasta (excl.) on fecha_creacion. Own lists (GET /payments/me) accept the
    same filters but never usuario_id: the owner comes from the token.
    """
    if "usuario_id" in args:
        raise invalid_input("Query parameter 'usuario_id' is not accepted; filter by pedido_id instead.")
    filters = {
        "pedido_id": _int_arg(args, "pedido_id", None, 1, MAX_BIGINT),
        "estado": _choice_arg(args, "estado", PAYMENT_STATUSES),
        "metodo_pago": _choice_arg(args, "metodo_pago", PAYMENT_METHODS),
        "desde": _datetime_arg(args, "desde", end_of_day=False),
        "hasta": _datetime_arg(args, "hasta", end_of_day=True),
        "usuario_id": None,
    }
    if filters["desde"] and filters["hasta"] and filters["desde"] >= filters["hasta"]:
        raise invalid_input("'desde' must be earlier than 'hasta'.")
    return filters
