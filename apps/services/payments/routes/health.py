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
    """
    healthy     (200): PostgreSQL and Redis answer.
    unavailable (503): either one does not. Like Orders, there is no
                       "degraded" state: every Payments endpoint needs a
                       token (revocation check in Redis) and PostgreSQL.
    """
    database_status = _database_status()
    redis_status = _redis_status()
    healthy = database_status == "connected" and redis_status == "connected"

    response = jsonify(
        {
            "success": healthy,
            "service": "payments",
            "status": "healthy" if healthy else "unavailable",
            "database": database_status,
            "redis": redis_status,
        }
    )
    response.status_code = 200 if healthy else 503
    return response
