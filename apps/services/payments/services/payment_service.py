"""
Business rules of the payments microservice.

Flow (matches the pagos model of migration 07, where 'pending' means
"registered, not confirmed"):

    1. POST /payments                 owner (or ADMIN) registers an attempt -> pagos 'pending'
                                      monto = pedidos.total (never from the client)
    2. POST /payments/<id>/approve    ADMIN confirms: pagos 'approved' + pedidos 'paid'
       POST /payments/<id>/reject     ADMIN rejects:  pagos 'rejected', order untouched
    3. POST /payments/<id>/refund     ADMIN refunds:  pagos 'refunded' + pedidos 'cancelled'
                                      + stock restored from pedido_detalle

Every write is ONE PostgreSQL transaction that locks, in this order,
pedidos (FOR UPDATE, the same lock Orders takes to cancel), then the pagos
row, then -- only for a refund -- the libros rows ordered by ISBN.
Validation happens AFTER the locks, on the current state, so concurrent
approvals/refunds/cancellations of one order run one after another and the
loser sees the winner's result (409). The constraints remain the last
barrier and are translated by name:

    ux_pagos_un_aprobado_por_pedido -> 409 PAYMENT_ALREADY_APPROVED
    uq_pagos_referencia             -> 409 PAYMENT_REFERENCE_EXISTS
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any
import uuid

import psycopg

from db.connection import open_connection, transaction
from repositories import payment_repository as repo
from services import catalog_cache, status
from utils.errors import (
    ServiceError,
    invalid_payment_transition,
    order_not_found,
    order_not_payable,
    payment_already_approved,
    payment_already_refunded,
    payment_amount_mismatch,
    payment_not_found,
    reference_already_exists,
    refund_not_allowed,
    transaction_conflict,
    user_inactive,
)


logger = logging.getLogger("payments_microservice.payments")

ONE_APPROVED_INDEX = "ux_pagos_un_aprobado_por_pedido"
REFERENCE_UNIQUE = "uq_pagos_referencia"


def _money(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def payment_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pago_id": row["pago_id"],
        "pedido_id": row["pedido_id"],
        "usuario_id": row["usuario_id"],
        "monto": _money(row["monto"]),
        "metodo_pago": row["metodo_pago"],
        "estado": row["estado"],
        "referencia": row["referencia"],
        "fecha_pago": _iso(row["fecha_pago"]),
        "fecha_creacion": _iso(row["fecha_creacion"]),
        "fecha_actualizacion": _iso(row["fecha_actualizacion"]),
    }


def _order_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {"pedido_id": row["pedido_id"], "estado": row["estado"], "total": _money(row["total"])}


def _constraint_name(exc: psycopg.Error) -> str | None:
    diag = getattr(exc, "diag", None)
    return getattr(diag, "constraint_name", None) if diag is not None else None


def _translate_db_error(exc: psycopg.Error) -> ServiceError | None:
    if isinstance(exc, (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure)):
        return transaction_conflict()
    if isinstance(exc, psycopg.errors.UniqueViolation):
        if _constraint_name(exc) == ONE_APPROVED_INDEX:
            return payment_already_approved()
        if _constraint_name(exc) == REFERENCE_UNIQUE:
            return reference_already_exists()
    return None


def _run(work):
    """Runs `work(conn)` in one transaction; known DB errors -> 409."""
    try:
        with transaction() as conn:
            return work(conn)
    except psycopg.Error as exc:
        translated = _translate_db_error(exc)
        if translated is None:
            raise
        raise translated from exc


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_payments(filters: dict[str, Any], limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    with open_connection() as conn:
        rows = repo.list_payments(conn, filters, limit, offset)
        total = repo.count_payments(conn, filters)
    return [payment_to_public(r) for r in rows], total


def get_payment(pago_id: int, user_id: int, is_admin: bool) -> dict[str, Any]:
    with open_connection() as conn:
        row = repo.get_payment(conn, pago_id)
    # Someone else's payment answers exactly like a missing one.
    if row is None or (not is_admin and row["usuario_id"] != user_id):
        raise payment_not_found()
    return payment_to_public(row)


def list_order_payments(pedido_id: int, user_id: int, is_admin: bool) -> dict[str, Any]:
    with open_connection() as conn:
        order = repo.get_order(conn, pedido_id)
        if order is None or (not is_admin and order["usuario_id"] != user_id):
            raise order_not_found()
        rows = repo.list_payments(conn, {"pedido_id": pedido_id}, 1000, 0)
    return {"order": _order_summary(order), "payments": [payment_to_public(r) for r in rows]}


# ---------------------------------------------------------------------------
# 1. Register an attempt
# ---------------------------------------------------------------------------

def _new_reference() -> str:
    return f"PAY-{uuid.uuid4().hex.upper()}"


def create_payment(values: dict[str, Any], user_id: int, is_admin: bool) -> dict[str, Any]:
    referencia = values["referencia"] or _new_reference()

    def work(conn):
        if not repo.get_user_activo(conn, user_id):
            raise user_inactive()

        order = repo.lock_order(conn, values["pedido_id"])
        if order is None or (not is_admin and order["usuario_id"] != user_id):
            raise order_not_found()
        if order["estado"] != status.ORDER_PENDING:
            raise order_not_payable(order["estado"], f"Only pending orders can be paid; this one is '{order['estado']}'.")
        if order["total"] <= 0:
            raise order_not_payable(order["estado"], "The order total is 0; there is nothing to pay.")

        # The amount is the order total, copied (frozen) into the payment.
        pago_id = repo.insert_payment(conn, order["pedido_id"], order["total"], values["metodo_pago"], referencia)
        return repo.get_payment(conn, pago_id)

    row = _run(work)
    logger.info("Payment %s registered for order %s by user %s", row["pago_id"], row["pedido_id"], user_id)
    return payment_to_public(row)


# ---------------------------------------------------------------------------
# 2. Confirm: approve / reject (ADMIN)
# ---------------------------------------------------------------------------

def _lock_order_and_payment(conn, pago_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """pedidos first (the lock Orders also takes), then the pagos row."""
    snapshot = repo.get_payment(conn, pago_id)
    if snapshot is None:
        raise payment_not_found()
    order = repo.lock_order(conn, snapshot["pedido_id"])  # pedido_id of a payment never changes
    payment = repo.lock_payment(conn, pago_id)
    return order, payment


def _require_pending_payment(payment: dict[str, Any], requested: str) -> None:
    current = payment["estado"]
    if current == status.PAYMENT_PENDING:
        return
    if current == status.PAYMENT_APPROVED and requested == status.PAYMENT_APPROVED:
        raise payment_already_approved()
    if current == status.PAYMENT_REFUNDED:
        raise payment_already_refunded()
    raise invalid_payment_transition(current, requested)


def approve_payment(pago_id: int, actor_id: int) -> dict[str, Any]:
    def work(conn):
        order, payment = _lock_order_and_payment(conn, pago_id)
        _require_pending_payment(payment, status.PAYMENT_APPROVED)

        if order["estado"] != status.ORDER_PENDING:
            # e.g. cancelled by Orders, or already paid through another attempt.
            raise order_not_payable(order["estado"], f"The order is '{order['estado']}' and can no longer be paid.")
        if repo.approved_payment_exists(conn, order["pedido_id"]):
            raise payment_already_approved()
        if payment["monto"] != order["total"]:
            raise payment_amount_mismatch()

        repo.set_payment_status(conn, pago_id, status.PAYMENT_APPROVED, set_fecha_pago=True)
        repo.set_order_status(conn, order["pedido_id"], status.ORDER_PAID)
        return repo.get_payment(conn, pago_id), repo.get_order(conn, order["pedido_id"])

    payment, order = _run(work)
    logger.info("Payment %s approved by admin %s; order %s -> paid", pago_id, actor_id, order["pedido_id"])
    return {"payment": payment_to_public(payment), "order": _order_summary(order)}


def reject_payment(pago_id: int, actor_id: int) -> dict[str, Any]:
    """The order is NOT touched: it stays pending (new attempts allowed), stock unchanged."""

    def work(conn):
        order, payment = _lock_order_and_payment(conn, pago_id)
        _require_pending_payment(payment, status.PAYMENT_REJECTED)
        repo.set_payment_status(conn, pago_id, status.PAYMENT_REJECTED)
        return repo.get_payment(conn, pago_id), order

    payment, order = _run(work)
    logger.info("Payment %s rejected by admin %s", pago_id, actor_id)
    return {"payment": payment_to_public(payment), "order": _order_summary(order)}


# ---------------------------------------------------------------------------
# 3. Refund (ADMIN): approved -> refunded, order paid -> cancelled, stock back
# ---------------------------------------------------------------------------

def refund_payment(pago_id: int, actor_id: int) -> dict[str, Any]:
    def work(conn):
        order, payment = _lock_order_and_payment(conn, pago_id)

        if payment["estado"] == status.PAYMENT_REFUNDED:
            raise payment_already_refunded()
        if payment["estado"] != status.PAYMENT_APPROVED:
            raise refund_not_allowed(
                f"Only approved payments can be refunded; this one is '{payment['estado']}'.",
                {"payment_estado": payment["estado"], "order_estado": order["estado"]},
            )
        if order["estado"] != status.ORDER_PAID:
            # 'completed' is final in Orders' state machine.
            raise refund_not_allowed(
                f"Only paid orders can be refunded; this one is '{order['estado']}'.",
                {"payment_estado": payment["estado"], "order_estado": order["estado"]},
            )

        # Stock back exactly once: this branch is only reachable while the
        # order is 'paid', and the order row is locked until commit.
        items = repo.get_order_items(conn, order["pedido_id"])
        repo.lock_books(conn, [i["isbn"] for i in items])
        for item in items:
            repo.add_stock(conn, item["isbn"], item["cantidad"])

        repo.set_payment_status(conn, pago_id, status.PAYMENT_REFUNDED)
        repo.set_order_status(conn, order["pedido_id"], status.ORDER_CANCELLED)
        return repo.get_payment(conn, pago_id), repo.get_order(conn, order["pedido_id"]), items

    payment, order, items = _run(work)
    catalog_cache.invalidate_books(i["isbn"] for i in items)
    logger.info(
        "Payment %s refunded by admin %s; order %s -> cancelled (restocked %d line(s))",
        pago_id, actor_id, order["pedido_id"], len(items),
    )
    return {
        "payment": payment_to_public(payment),
        "order": _order_summary(order),
        "restocked": [{"isbn": i["isbn"], "cantidad": i["cantidad"]} for i in items],
    }
