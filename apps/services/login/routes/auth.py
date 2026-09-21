from __future__ import annotations

from flask import Blueprint, request, session

from services import auth_service
from utils.responses import service_route


auth_bp = Blueprint("auth", __name__)


def _json_body() -> dict:
    # silent=True: a malformed/absent JSON body becomes {} (handled as a
    # normal validation error further down), never a raw Werkzeug 400 with
    # an HTML body.
    return request.get_json(silent=True) or {}


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
        session.clear()
        session["user_id"] = user["id"]
        session["email"] = user["email"]
        return 200, {"success": True, "message": "Login successful", "user": user}

    return service_route(build)


@auth_bp.post("/logout")
def logout():
    def build(_response_format: str):
        # Not an error if there was no session to begin with.
        session.clear()
        return 200, {"success": True, "message": "Logged out"}

    return service_route(build)


@auth_bp.get("/session")
def get_session():
    def build(_response_format: str):
        user_id = session.get("user_id")
        if not user_id:
            return 200, {"success": True, "authenticated": False}

        return (
            200,
            {
                "success": True,
                "authenticated": True,
                "user": {"id": user_id, "email": session.get("email")},
            },
        )

    return service_route(build)


@auth_bp.get("/verify-email")
def verify_email():
    def build(_response_format: str):
        token = request.args.get("token", "")
        result = auth_service.verify_email(token)
        return 200, {"success": True, "message": result["message"]}

    return service_route(build)
