from __future__ import annotations

import logging

from flask import Flask
from werkzeug.exceptions import HTTPException

from config import ConfigurationError, get_settings
from routes.auth import auth_bp
from routes.health import health_bp
from utils.errors import ServiceError, internal_error
from utils.responses import error_response, get_response_format


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("login_microservice")


def _safe_format() -> str:
    try:
        return get_response_format()
    except ServiceError:
        return "xml"


def create_app() -> Flask:
    # Fail fast when required environment variables are missing.
    settings = get_settings()

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
    )

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)

    # Catches Flask/Werkzeug's own HTTP errors (404 on unknown routes, 405
    # on a wrong method, ...) so this service never falls back to an HTML
    # error page, matching the same XML/JSON contract as every other error.
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        service_error = ServiceError(
            (error.name or "HTTP_ERROR").upper().replace(" ", "_"),
            error.description or error.name or "HTTP error",
            error.code or 500,
        )
        return error_response(service_error, _safe_format())

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        if isinstance(error, HTTPException):
            return handle_http_exception(error)
        logger.exception("Unhandled exception")
        return error_response(internal_error(), _safe_format())

    return app


if __name__ == "__main__":
    try:
        app_settings = get_settings()
        application = create_app()
        application.run(
            host=app_settings.flask_host,
            port=app_settings.flask_port,
            debug=app_settings.flask_debug,
        )
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from exc
