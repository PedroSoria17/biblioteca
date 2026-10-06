from __future__ import annotations

import logging

from flask import Flask
from library_shared.cors import init_cors
from library_shared.flask_auth import init_auth
from library_shared.redis_client import RedisGateway
from werkzeug.exceptions import HTTPException

from config import ConfigurationError, get_security_settings, get_settings
from routes.auth import auth_bp
from routes.health import health_bp
from utils.errors import ServiceError, internal_error
from utils.responses import auth_error_response, error_response, get_response_format


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


def create_app(redis_gateway: RedisGateway | None = None) -> Flask:
    """
    `redis_gateway` is only injected by tests; normally it is built from
    REDIS_URL. Building it does not connect yet, so the app still starts if
    Redis is down: /health reports it and auth endpoints answer 503.
    """
    # Fail fast when required environment variables are missing.
    settings = get_settings()
    security = get_security_settings()

    app = Flask(__name__)
    # Authentication no longer uses the Flask cookie session (it is now
    # JWT + Redis). SECRET_KEY stays configured for Flask itself.
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
    )

    gateway = redis_gateway or RedisGateway.from_settings(security.redis)
    init_auth(
        app,
        security.jwt,
        gateway,
        error_renderer=lambda error: auth_error_response(error, _safe_format()),
    )
    init_cors(app, security.cors)

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
