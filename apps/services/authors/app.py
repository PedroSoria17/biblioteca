from __future__ import annotations

import logging

import psycopg
from flask import Flask
from library_shared.cors import init_cors
from library_shared.errors import RedisUnavailableError, auth_backend_unavailable
from library_shared.flask_auth import default_error_renderer, init_auth
from library_shared.redis_client import RedisGateway
from werkzeug.exceptions import HTTPException

from config import ConfigurationError, get_security_settings, get_settings
from routes.health import health_bp
from routes.authors import authors_bp
from utils.errors import ServiceError, database_unavailable, internal_error
from utils.responses import error_response


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("authors_microservice")


def create_app(redis_gateway: RedisGateway | None = None) -> Flask:
    """
    `redis_gateway` is only injected by tests; normally it is built from
    REDIS_URL. Building it does not connect yet, so the app still starts if
    Redis is down: /health reports "degraded", public GETs keep working
    and protected endpoints answer 503.
    """
    # Fail fast when required environment variables are missing.
    get_settings()
    security = get_security_settings()

    app = Flask(__name__)
    # Keep the declared field order in JSON responses.
    app.json.sort_keys = False

    gateway = redis_gateway or RedisGateway.from_settings(security.redis)
    # Default renderer: {"success": false, "code": ..., "message": ...},
    # the same JSON shape as every ServiceError of this service.
    init_auth(app, security.jwt, gateway, error_renderer=default_error_renderer)
    init_cors(app, security.cors)

    app.register_blueprint(health_bp)
    app.register_blueprint(authors_bp)

    @app.errorhandler(ServiceError)
    def handle_service_error(error: ServiceError):
        return error_response(error)

    @app.errorhandler(RedisUnavailableError)
    def handle_redis_unavailable(_error: RedisUnavailableError):
        # Infrastructure failure, never disguised as 401: fail closed.
        logger.error("Redis unavailable while serving an authors endpoint")
        return default_error_renderer(auth_backend_unavailable()), 503

    @app.errorhandler(psycopg.OperationalError)
    def handle_database_unavailable(_error: psycopg.OperationalError):
        # Only the type: psycopg messages can include host/user.
        logger.error("PostgreSQL unavailable (%s)", type(_error).__name__)
        return error_response(database_unavailable())

    # Flask/Werkzeug's own HTTP errors (404 unknown route, 405 wrong
    # method, 415...) as JSON instead of an HTML page.
    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        return error_response(
            ServiceError(
                (error.name or "HTTP_ERROR").upper().replace(" ", "_"),
                error.description or error.name or "HTTP error",
                error.code or 500,
            )
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        if isinstance(error, HTTPException):
            return handle_http_exception(error)
        logger.exception("Unhandled exception")
        return error_response(internal_error())

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
