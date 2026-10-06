"""
Business rules of the orders microservice.

Creating an order is ONE PostgreSQL transaction (db.connection.transaction):

    BEGIN
      usuarios: exists and activo            (FOR KEY SHARE)
      libros:   lock every requested book    (FOR UPDATE, ordered by ISBN)
      validate existence and stock of every line
      INSERT pedidos                         (estado/total from DEFAULTs)
      INSERT pedido_detalle per line         (precio_unitario = libros.precio, frozen)
      UPDATE libros SET stock = stock - cantidad
      re-read pedidos                        (total set by the trigger)
    COMMIT
    -> invalidate Books' cache for those ISBNs

Any exception inside the block rolls everything back: there is never an
order without lines, a line without its order, or stock taken without an
order. libros_stock_check (stock >= 0) is the last barrier against
overselling; the row locks make it unreachable in practice.

Cancelling (pending -> cancelled) is also ONE transaction: the order row is
locked first, so a second cancellation waits, then sees 'cancelled' and is
refused: stock is restored exactly once.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any

import psycopg

from db.connection import open_connection, transaction
from repositories import order_repository as repo
from services import catalog_cache, status
from utils.errors import (
    ServiceError,
    book_not_found,
    insufficient_stock,
    invalid_status_transition,
    order_already_cancelled,
    order_not_found,
    transaction_conflict,
    user_inactive,
)


logger = logging.getLogger("orders_microservice.orders")

STOCK_CHECK = "libros_stock_check"
ORDER_USER_FK = "fk_pedidos_usuario"


def _money(value: Any) -> str | None:
    # Same convention as Books (Decimal -> str): no float rounding.
    return str(value) if isinstance(value, Decimal) else value


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def order_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pedido_id": row["pedido_id"],
        "usuario_id": row["usuario_id"],
        "estado": row["estado"],
        "total": _money(row["total"]),
        "items_count": int(row.get("items_count") or 0),
        "fecha_creacion": _iso(row["fecha_creacion"]),
        "fecha_actualizacion": _iso(row["fecha_actualizacion"]),
    }


def item_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "isbn": row["isbn"],
        "titulo": row["titulo"],
        "cantidad": row["cantidad"],
        "precio_unitario": _money(row["precio_unitario"]),
        "subtotal": _money(row["subtotal"]),
    }


def _constraint_name(exc: psycopg.Error) -> str | None:
    diag = getattr(exc, "diag", None)
    return getattr(diag, "constraint_name", None) if diag is not None else None


def _translate_db_error(exc: psycopg.Error) -> ServiceError | None:
    """Known, expected database errors -> controlled answers (never a 500)."""
    if isinstance(exc, (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure)):
        return transaction_conflict()
    if isinstance(exc, psycopg.errors.CheckViolation) and _constraint_name(exc) == STOCK_CHECK:
        return insufficient_stock([])
    if isinstance(exc, psycopg.errors.ForeignKeyViolation) and _constraint_name(exc) == ORDER_USER_FK:
        return user_inactive()
    return None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_orders(filters: dict[str, Any], limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    with open_connection() as conn:
        rows = repo.list_orders(conn, filters, limit, offset)
        total = repo.count_orders(conn, filters)
    return [order_to_public(r) for r in rows], total


def _visible_order(conn, pedido_id: int, user_id: int, is_admin: bool) -> dict[str, Any]:
    """
    ADMIN sees every order. A USER only sees its own: someone else's order
    answers 404 exactly like a missing one, so order ids cannot be probed.
    """
    row = repo.get_order(conn, pedido_id)
    if row is None or (not is_admin and row["usuario_id"] != user_id):
        raise order_not_found()
    return row


def get_order(pedido_id: int, user_id: int, is_admin: bool) -> dict[str, Any]:
    with open_connection() as conn:
        row = _visible_order(conn, pedido_id, user_id, is_admin)
    return order_to_public(row)


def get_items(pedido_id: int, user_id: int, is_admin: bool) -> dict[str, Any]:
    with open_connection() as conn:
        row = _visible_order(conn, pedido_id, user_id, is_admin)
        items = repo.list_items(conn, pedido_id)
    return {"order": order_to_public(row), "items": [item_to_public(i) for i in items]}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_order(user_id: int, lines: dict[str, int]) -> dict[str, Any]:
    """`lines` = {isbn: cantidad}, already validated and consolidated."""
    isbns = sorted(lines)
    try:
        with transaction() as conn:
            activo = repo.get_user_activo(conn, user_id)
            if not activo:
                raise user_inactive()

            books = repo.lock_books(conn, isbns)

            missing = [isbn for isbn in isbns if isbn not in books]
            if missing:
                raise book_not_found(missing)

            short = [
                {"isbn": isbn, "requested": lines[isbn], "available": books[isbn]["stock"]}
                for isbn in isbns
                if books[isbn]["stock"] < lines[isbn]
            ]
            if short:
                raise insufficient_stock(short)

            pedido_id = repo.insert_order(conn, user_id)
            for isbn in isbns:
                repo.insert_item(conn, pedido_id, isbn, lines[isbn], books[isbn]["precio"])
            for isbn in isbns:
                repo.change_stock(conn, isbn, -lines[isbn])

            order = repo.get_order(conn, pedido_id)
            items = repo.list_items(conn, pedido_id)
    except psycopg.Error as exc:
        translated = _translate_db_error(exc)
        if translated is None:
            raise
        raise translated from exc

    catalog_cache.invalidate_books(isbns)
    logger.info("Order %s created by user %s (%d line(s))", pedido_id, user_id, len(isbns))
    return {**order_to_public(order), "items": [item_to_public(i) for i in items]}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def change_status(pedido_id: int, requested: str, actor_id: int) -> dict[str, Any]:
    restocked: list[str] = []
    try:
        with transaction() as conn:
            order = repo.get_order(conn, pedido_id, for_update=True)
            if order is None:
                raise order_not_found()

            current = order["estado"]
            if current == status.CANCELLED and requested == status.CANCELLED:
                raise order_already_cancelled()
            reason = status.transition_error_reason(current, requested)
            if reason is not None:
                raise invalid_status_transition(current, requested, reason)

            if status.restores_stock(current, requested):
                items = repo.get_order_items_for_restock(conn, pedido_id)
                restocked = [item["isbn"] for item in items]
                repo.lock_books(conn, restocked)  # same ISBN order as creation
                for item in items:
                    repo.change_stock(conn, item["isbn"], item["cantidad"])

            repo.set_status(conn, pedido_id, requested)
            updated = repo.get_order(conn, pedido_id)
    except psycopg.Error as exc:
        translated = _translate_db_error(exc)
        if translated is None:
            raise
        raise translated from exc

    catalog_cache.invalidate_books(restocked)
    logger.info(
        "Order %s: %s -> %s by admin %s (restocked %d line(s))",
        pedido_id, current, requested, actor_id, len(restocked),
    )
    return order_to_public(updated)
