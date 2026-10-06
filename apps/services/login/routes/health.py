from __future__ import annotations

from flask import Blueprint, current_app
from library_shared.flask_auth import EXTENSION_KEY

from db.connection import open_connection
from utils.responses import service_route


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
    def build(_response_format: str):
        database_status = _database_status()
        redis_status = _redis_status()

        # Redis is critical for login (sessions, refresh tokens, revocation),
        # so the service is only healthy when both backends answer.
        healthy = database_status == "connected" and redis_status == "connected"
        return (
            200 if healthy else 503,
            {
                "success": healthy,
                "service": "login",
                "status": "healthy" if healthy else "unhealthy",
                "database": database_status,
                "redis": redis_status,
            },
        )

    return service_route(build)
