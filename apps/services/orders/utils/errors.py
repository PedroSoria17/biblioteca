from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ServiceError(Exception):
    """
    Controlled JSON error for every endpoint of the orders microservice.
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
    # Owner, prices, totals, status and timestamps are decided by the
    # server / PostgreSQL, never by the client.
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

def order_not_found() -> ServiceError:
    # Also used for orders that exist but belong to someone else: a USER
    # cannot learn which order ids exist.
    return ServiceError("ORDER_NOT_FOUND", "Order not found.", 404)


def book_not_found(isbns: list[str]) -> ServiceError:
    return ServiceError("BOOK_NOT_FOUND", "One or more books do not exist.", 404, {"isbns": isbns})


# --- 409 ---------------------------------------------------------------------

def insufficient_stock(items: list[dict]) -> ServiceError:
    return ServiceError("INSUFFICIENT_STOCK", "Not enough stock for one or more books.", 409, {"items": items})


def invalid_status_transition(current: str, requested: str, reason: str) -> ServiceError:
    return ServiceError(
        "INVALID_STATUS_TRANSITION",
        reason,
        409,
        {"from": current, "to": requested},
    )


def order_already_cancelled() -> ServiceError:
    return ServiceError("ORDER_ALREADY_CANCELLED", "The order is already cancelled.", 409)


def transaction_conflict() -> ServiceError:
    # Deadlock / serialization failure detected by PostgreSQL: the whole
    # transaction was rolled back, the client can retry.
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
