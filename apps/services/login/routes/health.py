from __future__ import annotations

from flask import Blueprint

from db.connection import open_connection
from utils.responses import service_route


health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    def build(_response_format: str):
        try:
            with open_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            database_status = "connected"
        except Exception:
            # Intentionally generic: never leak host/port/credentials from
            # the underlying connection error.
            database_status = "unavailable"

        healthy = database_status == "connected"
        return (
            200 if healthy else 503,
            {
                "success": healthy,
                "service": "login",
                "status": "healthy" if healthy else "unhealthy",
                "database": database_status,
            },
        )

    return service_route(build)
