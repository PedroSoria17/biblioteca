from __future__ import annotations

from flask import Blueprint, current_app, request
from library_shared.flask_auth import EXTENSION_KEY, AuthContext, authenticate_request, extract_bearer_token

from services import auth_service, token_service
from utils.responses import service_route


auth_bp = Blueprint("auth", __name__)


def _json_body() -> dict:
    # silent=True: a malformed/absent JSON body becomes {} (handled as a
    # normal validation error further down), never a raw Werkzeug 400 with
    # an HTML body.
    return request.get_json(silent=True) or {}


def _auth_context() -> AuthContext:
    # Registered by library_shared.flask_auth.init_auth in app.create_app.
    return current_app.extensions[EXTENSION_KEY]


@auth_bp.post("/register")
def register():
    def build(_response_format: str):
        user = auth_service.register_user(_json_body())
        return (
            201,
            {
                "success": True,
                "message": "User registered. Check your email to verify your account.",
                "user": user,
            },
        )

    return service_route(build)


@auth_bp.post("/login")
def login():
    def build(_response_format: str):
        user = auth_service.login_user(_json_body())
        context = _auth_context()
        tokens = token_service.start_session(user, context.jwt_settings, context.gateway)
        return 200, {"success": True, "message": "Login successful", "user": user, **tokens}

    return service_route(build)


@auth_bp.post("/refresh")
def refresh():
    """Expects `Authorization: Bearer <refresh_token>`; access tokens are rejected."""

    def build(_response_format: str):
        refresh_token = extract_bearer_token(request.headers.get("Authorization"))
        context = _auth_context()
        result = token_service.refresh_session(refresh_token, context.jwt_settings, context.gateway)
        return 200, {"success": True, "message": "Token refreshed", **result}

    return service_route(build)


@auth_bp.post("/logout")
def logout():
    """Expects `Authorization: Bearer <access_token>`."""

    def build(_response_format: str):
        claims = authenticate_request()
        token_service.end_session(claims, _auth_context().gateway)
        return 200, {"success": True, "message": "Logged out"}

    return service_route(build)


@auth_bp.get("/session")
def get_session():
    def build(_response_format: str):
        # Same contract as before for anonymous callers: 200 + authenticated=false.
        if not request.headers.get("Authorization"):
            return 200, {"success": True, "authenticated": False}

        claims = authenticate_request()
        user = token_service.describe_session(claims, _auth_context().gateway)
        return 200, {"success": True, "authenticated": True, "user": user}

    return service_route(build)


@auth_bp.get("/verify-email")
def verify_email():
    def build(_response_format: str):
        token = request.args.get("token", "")
        result = auth_service.verify_email(token)
        return 200, {"success": True, "message": result["message"]}

    return service_route(build)
