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
    degraded    (200): PostgreSQL answers, Redis does not. Public GETs keep
                       working; every write answers 503 (revocation cannot
                       be checked). 200 so a proxy keeps routing the reads.
    unavailable (503): PostgreSQL does not answer; nothing can be served.
    """
    database_status = _database_status()
    redis_status = _redis_status()

    if database_status != "connected":
        status, http_status = "unavailable", 503
    elif redis_status != "connected":
        status, http_status = "degraded", 200
    else:
        status, http_status = "healthy", 200

    response = jsonify(
        {
            "success": status == "healthy",
            "service": "authors",
            "status": status,
            "database": database_status,
            "redis": redis_status,
            "public_reads": "available" if database_status == "connected" else "unavailable",
            "writes": "available" if status == "healthy" else "unavailable",
        }
    )
    response.status_code = http_status
    return response
