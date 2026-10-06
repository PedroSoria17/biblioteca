"""
Flask integration: Bearer extraction, 401/403 handling and role checks.

Usage in a service (next phases):

    from library_shared.flask_auth import init_auth, require_auth, require_roles
    from library_shared.roles import ROLE_ADMIN

    init_auth(app, jwt_settings, redis_gateway, error_renderer=my_xml_json_renderer)

    @app.post("/books")
    @require_roles(ROLE_ADMIN)
    def create_book(): ...

401 = the caller is not authenticated (missing/invalid/expired/revoked token).
403 = authenticated, but its role_id is not allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Callable

from flask import Flask, Response, current_app, g, jsonify, request

from library_shared.errors import AuthError, forbidden, malformed_authorization_header, missing_token
from library_shared.jwt_tokens import TokenClaims
from library_shared.redis_client import RedisGateway
from library_shared.settings import JwtSettings
from library_shared.token_store import authenticate_access_token


EXTENSION_KEY = "library_shared.auth"

ErrorRenderer = Callable[[AuthError], Response]


@dataclass(frozen=True)
class AuthContext:
    jwt_settings: JwtSettings
    gateway: RedisGateway


def default_error_renderer(error: AuthError) -> Response:
    response = jsonify({"success": False, "code": error.code, "message": error.message})
    response.status_code = error.http_status
    return response


def init_auth(
    app: Flask,
    jwt_settings: JwtSettings,
    gateway: RedisGateway,
    error_renderer: ErrorRenderer | None = None,
) -> None:
    """
    Registers the auth context and an AuthError handler. Pass
    `error_renderer` to keep a service's own XML/JSON error format.
    """
    app.extensions[EXTENSION_KEY] = AuthContext(jwt_settings=jwt_settings, gateway=gateway)
    renderer = error_renderer or default_error_renderer

    @app.errorhandler(AuthError)
    def _handle_auth_error(error: AuthError):
        response = renderer(error)
        response.status_code = error.http_status
        if error.http_status == 401:
            response.headers["WWW-Authenticate"] = 'Bearer realm="library"'
        return response


def extract_bearer_token(header_value: str | None) -> str:
    if header_value is None or not header_value.strip():
        raise missing_token()

    parts = header_value.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise malformed_authorization_header()

    return parts[1]


def authenticate_request() -> TokenClaims:
    context: AuthContext = current_app.extensions[EXTENSION_KEY]
    token = extract_bearer_token(request.headers.get("Authorization"))
    claims = authenticate_access_token(token, context.jwt_settings, context.gateway)
    g.auth_claims = claims
    return claims


def current_claims() -> TokenClaims | None:
    return g.get("auth_claims")


def require_auth(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        authenticate_request()
        return view(*args, **kwargs)

    return wrapper


def require_roles(*role_ids: int):
    if not role_ids:
        raise ValueError("require_roles needs at least one role_id.")
    allowed = frozenset(role_ids)

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            claims = authenticate_request()  # 401 first...
            if claims.role_id not in allowed:
                raise forbidden()  # ...403 only for an authenticated caller.
            return view(*args, **kwargs)

        return wrapper

    return decorator
