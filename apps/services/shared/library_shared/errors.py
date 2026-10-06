from __future__ import annotations

from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class RedisUnavailableError(RuntimeError):
    """
    Redis could not serve a CRITICAL operation (sessions, refresh tokens,
    JWT revocation). Callers must fail closed: never grant access because
    this was raised.
    """


@dataclass
class AuthError(Exception):
    """
    Controlled authentication/authorization error. Services render it with
    their own wire format (XML/JSON) through the handler registered in
    library_shared.flask_auth.init_auth.
    """

    code: str
    message: str
    http_status: int

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def missing_token() -> AuthError:
    return AuthError("MISSING_TOKEN", "Authorization header with a Bearer token is required.", 401)


def malformed_authorization_header() -> AuthError:
    return AuthError("INVALID_AUTHORIZATION_HEADER", "Authorization header must be 'Bearer <token>'.", 401)


def invalid_token() -> AuthError:
    # Deliberately generic: never tells the caller WHICH check failed
    # (signature, algorithm, claims...), only that the token is unusable.
    return AuthError("INVALID_TOKEN", "Token is invalid.", 401)


def token_expired() -> AuthError:
    return AuthError("TOKEN_EXPIRED", "Token has expired.", 401)


def token_revoked() -> AuthError:
    return AuthError("TOKEN_REVOKED", "Token has been revoked.", 401)


def forbidden() -> AuthError:
    return AuthError("FORBIDDEN", "You do not have permission to perform this operation.", 403)


def auth_backend_unavailable() -> AuthError:
    # 503 (not 401): the token may be perfectly valid, but revocation could
    # not be verified, so the request is refused without telling the client
    # to discard its credentials.
    return AuthError(
        "AUTH_BACKEND_UNAVAILABLE",
        "Authentication backend temporarily unavailable.",
        503,
    )
