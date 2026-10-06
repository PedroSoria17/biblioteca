"""
Order status machine.

The states are the ones fixed by ck_pedidos_estado in
data/07_microservices_auth_orders_payments.sql, with the meaning documented
there:

    pending   -> created, waiting for payment (only editable state; DEFAULT)
    paid      -> an APPROVED payment for the total exists
    completed -> delivered / closed
    cancelled -> cancelled (from pending, or from paid WITH a refund)

The CHECK accepts any of the four strings; this module decides which
changes are legal, and which service is allowed to perform them:

    pending -> cancelled   Orders (ADMIN). Restores the reserved stock.
    paid    -> completed   Orders (ADMIN).
    pending -> paid        Payments (phase 7), in the same transaction that
                           approves the payment. Orders refuses it: marking
                           an order as paid without an approved payment
                           would break the meaning of `paid`.
    paid    -> cancelled   Payments (phase 7), together with the refund
                           (pagos.estado = 'refunded'). Orders refuses it.
    completed, cancelled   final states.

Payments should import ORDER_TRANSITIONS / restore rules from here instead
of redefining them.
"""

from __future__ import annotations


PENDING = "pending"
PAID = "paid"
COMPLETED = "completed"
CANCELLED = "cancelled"

STATUSES = (PENDING, PAID, COMPLETED, CANCELLED)
FINAL_STATUSES = frozenset({COMPLETED, CANCELLED})

# Every legal transition of the domain.
ORDER_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (PENDING, CANCELLED),
        (PAID, COMPLETED),
        (PENDING, PAID),
        (PAID, CANCELLED),
    }
)

# The subset that PATCH /orders/<id>/status (Orders, ADMIN) may perform.
ORDERS_SERVICE_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (PENDING, CANCELLED),
        (PAID, COMPLETED),
    }
)

_PAYMENTS_ONLY_REASON = {
    (PENDING, PAID): "An order becomes 'paid' only when Payments approves a payment for it.",
    (PAID, CANCELLED): "A paid order can only be cancelled by Payments together with its refund.",
}


def transition_error_reason(current: str, requested: str) -> str | None:
    """None if Orders may perform current -> requested, else the reason why not."""
    if (current, requested) in ORDERS_SERVICE_TRANSITIONS:
        return None
    if (current, requested) in _PAYMENTS_ONLY_REASON:
        return _PAYMENTS_ONLY_REASON[(current, requested)]
    if current in FINAL_STATUSES:
        return f"The order is '{current}', a final status."
    if current == requested:
        return f"The order is already '{current}'."
    return f"Cannot change an order from '{current}' to '{requested}'."


def restores_stock(current: str, requested: str) -> bool:
    """Stock was reserved at creation and is given back on cancellation."""
    return requested == CANCELLED and current in (PENDING, PAID)
