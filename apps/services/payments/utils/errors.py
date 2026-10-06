from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ServiceError(Exception):
    """
    Controlled JSON error for every endpoint of the payments microservice.
    Rendered by the handler registered in app.py as
    {"success": false, "code": ..., "message": ...} (same shape as the
    401/403/503 errors rendered by library_shared.flask_auth).
    """

    code: str
    message: str
    http_status: int = 400
    details: dict | None = field(default=None)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# --- 400 ---------------------------------------------------------------------

def invalid_input(message: str) -> ServiceError:
    return ServiceError("INVALID_INPUT", message, 400)


def invalid_body() -> ServiceError:
    return ServiceError("INVALID_INPUT", "Request body must be a JSON object.", 400)


def unknown_fields(names: list[str]) -> ServiceError:
    return ServiceError("UNKNOWN_FIELDS", "Request contains unknown fields.", 400, {"fields": names})


def fields_not_allowed(names: list[str]) -> ServiceError:
    # Amount, status, owner, ids and dates are decided by the server.
    return ServiceError(
        "FIELDS_NOT_ALLOWED",
        "These fields are managed by the server and cannot be sent.",
        400,
        {"fields": names},
    )


# --- 403 ---------------------------------------------------------------------

def user_inactive() -> ServiceError:
    return ServiceError("USER_INACTIVE", "The user does not exist or is inactive.", 403)


# --- 404 ---------------------------------------------------------------------

def payment_not_found() -> ServiceError:
    # Also for payments of someone else's order (existence is not revealed).
    return ServiceError("PAYMENT_NOT_FOUND", "Payment not found.", 404)


def order_not_found() -> ServiceError:
    return ServiceError("ORDER_NOT_FOUND", "Order not found.", 404)


# --- 409 ---------------------------------------------------------------------

def order_not_payable(estado: str, reason: str) -> ServiceError:
    return ServiceError("ORDER_NOT_PAYABLE", reason, 409, {"order_estado": estado})


def payment_already_approved() -> ServiceError:
    return ServiceError("PAYMENT_ALREADY_APPROVED", "The payment is already approved.", 409)


def payment_already_refunded() -> ServiceError:
    return ServiceError("PAYMENT_ALREADY_REFUNDED", "The payment is already refunded.", 409)


def invalid_payment_transition(current: str, requested: str) -> ServiceError:
    return ServiceError(
        "INVALID_PAYMENT_TRANSITION",
        f"Cannot change a payment from '{current}' to '{requested}'.",
        409,
        {"from": current, "to": requested},
    )


def refund_not_allowed(reason: str, details: dict) -> ServiceError:
    return ServiceError("REFUND_NOT_ALLOWED", reason, 409, details)


def payment_amount_mismatch() -> ServiceError:
    return ServiceError(
        "PAYMENT_AMOUNT_MISMATCH",
        "The payment amount no longer matches the order total.",
        409,
    )


def reference_already_exists() -> ServiceError:
    return ServiceError(
        "PAYMENT_REFERENCE_EXISTS",
        "A payment with this referencia is already registered.",
        409,
    )


def transaction_conflict() -> ServiceError:
    return ServiceError(
        "TRANSACTION_CONFLICT",
        "The operation conflicted with a concurrent one and was rolled back; retry it.",
        409,
    )


# --- 5xx ---------------------------------------------------------------------

def database_unavailable() -> ServiceError:
    return ServiceError("DATABASE_UNAVAILABLE", "Database temporarily unavailable.", 503)


def internal_error() -> ServiceError:
    return ServiceError(
        "INTERNAL_ERROR",
        "An internal error occurred while processing the request.",
        500,
    )
