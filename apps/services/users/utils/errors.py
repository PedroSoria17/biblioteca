from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ServiceError(Exception):
    """
    Controlled JSON error for every endpoint of the users microservice.
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
    # password_hash, es_administrador, fecha_registro, usuario_id: derived
    # or managed by the server/database, never accepted from a client.
    return ServiceError(
        "FIELDS_NOT_ALLOWED",
        "These fields are managed by the server and cannot be sent.",
        400,
        {"fields": names},
    )


def invalid_role() -> ServiceError:
    return ServiceError("INVALID_ROLE", "role_id does not exist.", 400)


# --- 404 ---------------------------------------------------------------------

def user_not_found() -> ServiceError:
    return ServiceError("USER_NOT_FOUND", "User not found.", 404)


# --- 409 ---------------------------------------------------------------------

def email_already_exists() -> ServiceError:
    return ServiceError("EMAIL_ALREADY_EXISTS", "Email is already in use.", 409)


def admin_already_exists() -> ServiceError:
    return ServiceError(
        "ADMIN_ALREADY_EXISTS",
        "An administrator already exists; only one ADMIN is allowed.",
        409,
    )


def admin_must_be_active() -> ServiceError:
    return ServiceError("ADMIN_MUST_BE_ACTIVE", "An ADMIN user must be active.", 409)


def last_admin_required() -> ServiceError:
    return ServiceError(
        "LAST_ADMIN_REQUIRED",
        "This operation would leave the system without an active administrator.",
        409,
    )


def user_has_order_history() -> ServiceError:
    return ServiceError(
        "USER_HAS_ORDER_HISTORY",
        "The user has orders and cannot be deleted; deactivate it instead (activo=false).",
        409,
    )


def user_has_dependencies() -> ServiceError:
    return ServiceError(
        "USER_HAS_DEPENDENCIES",
        "The user is referenced by other records and cannot be deleted.",
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
