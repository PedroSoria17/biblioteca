"""
Payment and order states used by Payments.

PAYMENT states (ck_pagos_estado, data/07_microservices_auth_orders_payments.sql):

    pending  -> registered, not confirmed (DEFAULT)
    approved -> confirmed (fecha_pago required by ck_pagos_fecha_pago)
    rejected -> rejected
    refunded -> refunded (only from a previously approved payment)

    pending -> approved     ADMIN confirms        order pending -> paid
    pending -> rejected     ADMIN rejects         order unchanged
    approved -> refunded    ADMIN refunds         order paid -> cancelled + stock back

ORDER states are those of ck_pedidos_estado, with the transitions of
apps/services/orders/services/status.py. Payments performs exactly the two
that Orders delegates to it (ORDER_TRANSITIONS minus
ORDERS_SERVICE_TRANSITIONS there):

    pending -> paid         together with pending -> approved
    paid    -> cancelled    together with approved -> refunded

The module is duplicated (not imported) because every service has its own
top-level `services` package; tests/test_status_contract.py loads Orders'
file and checks that both stay consistent.
"""

from __future__ import annotations


# Order states (ck_pedidos_estado).
ORDER_PENDING = "pending"
ORDER_PAID = "paid"
ORDER_COMPLETED = "completed"
ORDER_CANCELLED = "cancelled"

# Payment states (ck_pagos_estado).
PAYMENT_PENDING = "pending"
PAYMENT_APPROVED = "approved"
PAYMENT_REJECTED = "rejected"
PAYMENT_REFUNDED = "refunded"
PAYMENT_STATUSES = (PAYMENT_PENDING, PAYMENT_APPROVED, PAYMENT_REJECTED, PAYMENT_REFUNDED)

# Payment methods (ck_pagos_metodo).
PAYMENT_METHODS = ("credit_card", "debit_card", "bank_transfer", "cash")

PAYMENT_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (PAYMENT_PENDING, PAYMENT_APPROVED),
        (PAYMENT_PENDING, PAYMENT_REJECTED),
        (PAYMENT_APPROVED, PAYMENT_REFUNDED),
    }
)

# Order transitions performed by Payments (delegated by Orders).
ORDER_TRANSITIONS_BY_PAYMENTS: frozenset[tuple[str, str]] = frozenset(
    {
        (ORDER_PENDING, ORDER_PAID),
        (ORDER_PAID, ORDER_CANCELLED),
    }
)
