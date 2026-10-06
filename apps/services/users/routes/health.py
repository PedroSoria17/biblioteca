from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from library_shared.flask_auth import EXTENSION_KEY

from db.connection import open_connection


health_bp = Blueprint("health", __name__)


def _database_status() -> str:
    try:
        with open_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return "connected"
    except Exception:
        # Intentionally generic: never leak host/port/credentials from
        # the underlying connection error.
        return "unavailable"


def _redis_status() -> str:
    # RedisGateway.ping never raises and only logs the exception type.
    gateway = current_app.extensions[EXTENSION_KEY].gateway
    return "connected" if gateway.ping() else "unavailable"


@health_bp.get("/health")
def health():
    database_status = _database_status()
    redis_status = _redis_status()

    # Every endpoint except this one is protected, and protected endpoints
    # need Redis (JWT revocation): without it the service cannot serve any
    # authenticated request safely, so it is reported as unhealthy.
    healthy = database_status == "connected" and redis_status == "connected"
    response = jsonify(
        {
            "success": healthy,
            "service": "users",
            "status": "healthy" if healthy else "unhealthy",
            "database": database_status,
            "redis": redis_status,
        }
    )
    response.status_code = 200 if healthy else 503
    return response
