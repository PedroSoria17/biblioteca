from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServiceError(Exception):
    """
    Controlled, XML/JSON-serializable error for every endpoint of the login
    microservice. Raising one of the factories below (instead of a bare
    Exception) is what lets utils.responses.service_route turn it into a
    consistent, non-HTML response with the right HTTP status.
    """

    code: str
    message: str
    http_status: int = 400

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def invalid_format() -> ServiceError:
    return ServiceError("INVALID_FORMAT", "Supported formats are xml and json.", 400)


def invalid_input(message: str) -> ServiceError:
    return ServiceError("INVALID_INPUT", message, 400)


def invalid_credentials() -> ServiceError:
    # Deliberately identical whether the email does not exist or the
    # password is wrong: see auth_service.login_user.
    return ServiceError("INVALID_CREDENTIALS", "Invalid credentials", 401)


def email_already_registered() -> ServiceError:
    return ServiceError("EMAIL_ALREADY_REGISTERED", "Email already registered", 409)


def invalid_token() -> ServiceError:
    return ServiceError("INVALID_TOKEN", "Verification token is invalid.", 400)


def token_expired() -> ServiceError:
    return ServiceError("TOKEN_EXPIRED", "Verification token has expired.", 400)


def not_found(message: str = "Resource not found") -> ServiceError:
    return ServiceError("NOT_FOUND", message, 404)


def internal_error() -> ServiceError:
    return ServiceError(
        "INTERNAL_ERROR",
        "An internal error occurred while processing the request.",
        500,
    )


def service_unavailable(message: str = "Service temporarily unavailable") -> ServiceError:
    return ServiceError("SERVICE_UNAVAILABLE", message, 503)
