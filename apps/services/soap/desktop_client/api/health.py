"""
Health "traffic lights" for the six microservices.

Each service exposes GET /health with its own vocabulary; it is normalized
to three states:

    up        green   ok / healthy
    degraded  amber   degraded (e.g. Books or Authors with Redis down:
                      public reads still work, writes do not)
    down      red     unhealthy / unavailable / no answer / timeout

A 503 is NOT an exception here: its body still says what is failing.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json

from api.http import ApiClient, RawResponse, ServiceUnreachableError


UP, DEGRADED, DOWN = "up", "degraded", "down"

# Books needs ?details=true to check PostgreSQL/Redis (its plain /health is a liveness probe).
HEALTH_PARAMS = {"books": {"details": "true"}}

_STATUS_MAP = {"ok": UP, "healthy": UP, "degraded": DEGRADED}


@dataclass(frozen=True)
class ServiceHealth:
    service: str
    state: str
    detail: str


def _interpret(service: str, response: RawResponse) -> ServiceHealth:
    try:
        data = json.loads(response.body.decode("utf-8")) if response.body else {}
    except (ValueError, UnicodeDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status", "")).lower()
    if response.status >= 400:
        state = DEGRADED if status == "degraded" else DOWN
    elif status:
        state = _STATUS_MAP.get(status, DOWN)
    else:
        state = UP  # 200 without a status field: alive
    parts = [f"{k}: {data[k]}" for k in ("database", "redis") if k in data]
    detail = ", ".join(parts) or (status or f"HTTP {response.status}")
    return ServiceHealth(service, state, detail)


class HealthApi:
    def __init__(self, client: ApiClient, timeout: float = 3.0) -> None:
        self.client = client
        self.timeout = timeout

    def check(self, service: str) -> ServiceHealth:
        try:
            response = self.client.probe(service, "/health", params=HEALTH_PARAMS.get(service), timeout=self.timeout)
        except ServiceUnreachableError:  # connection refused, timeout, DNS...
            return ServiceHealth(service, DOWN, "sin respuesta")
        return _interpret(service, response)

    def check_all(self, services) -> list[ServiceHealth]:
        """All services in parallel: the slowest one bounds the total time."""
        services = list(services)
        with ThreadPoolExecutor(max_workers=len(services) or 1) as pool:
            return list(pool.map(self.check, services))
