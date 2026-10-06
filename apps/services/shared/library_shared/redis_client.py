"""
Redis access shared by every microservice.

Two families of operations, on purpose:

- cache_* (OPTIONAL): used for the books catalog cache. Any Redis failure is
  logged and swallowed; callers fall back to PostgreSQL.
- get/set/exists/delete/pop (CRITICAL): used for sessions, refresh tokens
  and JWT revocation. Any Redis failure raises RedisUnavailableError so the
  caller fails closed.

Every write requires an explicit TTL: nothing is stored in Redis forever.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import redis
from redis.exceptions import RedisError

from library_shared.errors import RedisUnavailableError
from library_shared.metrics import Metrics
from library_shared.redaction import redact_url
from library_shared.settings import RedisSettings


logger = logging.getLogger("library_shared.redis")

# Errors that mean "Redis could not answer", as opposed to programming errors.
REDIS_FAILURES = (RedisError, OSError)


def create_redis_client(settings: RedisSettings) -> redis.Redis:
    """
    Builds a client from REDIS_URL. The password travels inside the URL
    (redis://:password@host:6379/0), so it is never written in code. The
    connection is lazy: this does not touch the network.
    """
    logger.info("Configuring Redis client for %s", redact_url(settings.url))
    return redis.Redis.from_url(
        settings.url,
        socket_connect_timeout=settings.connect_timeout_seconds,
        socket_timeout=settings.socket_timeout_seconds,
        health_check_interval=settings.health_check_interval_seconds,
        retry_on_timeout=False,
        decode_responses=True,
    )


def require_ttl(ttl_seconds: int | float) -> int:
    ttl = int(math.ceil(ttl_seconds))
    if ttl <= 0:
        raise ValueError("Redis TTL must be a positive number of seconds.")
    return ttl


def ttl_until(expires_at_epoch: int | float, now: float | None = None) -> int:
    """Seconds left until an absolute expiry (e.g. a JWT exp), at least 1."""
    now = time.time() if now is None else now
    return max(1, int(math.ceil(expires_at_epoch - now)))


class RedisGateway:
    def __init__(
        self,
        client: Any,
        metrics: Metrics | None = None,
        cache_cooldown_seconds: float = 0.0,
    ) -> None:
        """
        cache_cooldown_seconds (opt-in, 0 = disabled): after an OPTIONAL
        cache read/write fails, skip cache reads/writes for that long and go
        straight to the source of truth, instead of paying the connect
        timeout on every request while Redis is down. Critical operations
        and invalidations are never skipped.
        """
        self._client = client
        self.metrics = metrics or Metrics()
        self._cache_cooldown_seconds = cache_cooldown_seconds
        self._cache_suspended_until = 0.0

    @classmethod
    def from_settings(
        cls,
        settings: RedisSettings,
        metrics: Metrics | None = None,
        cache_cooldown_seconds: float = 0.0,
    ) -> "RedisGateway":
        return cls(create_redis_client(settings), metrics, cache_cooldown_seconds)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        try:
            up = bool(self._client.ping())
        except REDIS_FAILURES as exc:
            self._record_failure("ping", exc)
            return False
        if up:
            self._cache_suspended_until = 0.0  # Redis proved reachable again.
        return up

    def health(self) -> dict[str, Any]:
        started = time.perf_counter()
        up = self.ping()
        result: dict[str, Any] = {"status": "up" if up else "down"}
        if up:
            result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    # ------------------------------------------------------------------
    # OPTIONAL operations (cache). Never raise on Redis failure.
    # ------------------------------------------------------------------

    def cache_get(self, key: str) -> str | None:
        if self._cache_suspended():
            return None
        try:
            value = self._client.get(key)
        except REDIS_FAILURES as exc:
            self._record_cache_failure("cache_get", exc)
            return None
        self.metrics.incr("cache_hit" if value is not None else "cache_miss")
        return value

    def cache_set(self, key: str, value: str, ttl_seconds: int | float) -> bool:
        ttl = require_ttl(ttl_seconds)
        if self._cache_suspended():
            return False
        try:
            self._client.set(key, value, ex=ttl)
            return True
        except REDIS_FAILURES as exc:
            self._record_cache_failure("cache_set", exc)
            return False

    def cache_delete(self, *keys: str) -> int:
        if not keys:
            return 0
        try:
            return int(self._client.delete(*keys))
        except REDIS_FAILURES as exc:
            self._record_failure("cache_delete", exc)
            return 0

    def cache_delete_pattern(self, pattern: str) -> int:
        """SCAN-based (never KEYS) so it does not block Redis on big keyspaces."""
        try:
            keys = list(self._client.scan_iter(match=pattern, count=500))
            return int(self._client.delete(*keys)) if keys else 0
        except REDIS_FAILURES as exc:
            self._record_failure("cache_delete_pattern", exc)
            return 0

    def cache_invalidate(self, keys: tuple[str, ...] = (), patterns: tuple[str, ...] = ()) -> bool:
        """
        Deletes exact keys and SCAN-matched patterns. Never raises and never
        skipped by the cooldown. Returns False if any part failed, so the
        caller can log/count a stale-cache window (bounded by the TTL).
        """
        ok = True
        if keys:
            try:
                self._client.delete(*keys)
            except REDIS_FAILURES as exc:
                self._record_cache_failure("cache_invalidate", exc)
                ok = False
        for pattern in patterns:
            try:
                matched = list(self._client.scan_iter(match=pattern, count=500))
                if matched:
                    self._client.delete(*matched)
            except REDIS_FAILURES as exc:
                self._record_cache_failure("cache_invalidate", exc)
                ok = False
        self.metrics.incr("cache_invalidation" if ok else "cache_invalidation_failed")
        return ok

    # ------------------------------------------------------------------
    # CRITICAL operations (security). Raise RedisUnavailableError.
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        return self._critical("get", lambda: self._client.get(key))

    def set(self, key: str, value: str, ttl_seconds: int | float) -> None:
        ttl = require_ttl(ttl_seconds)
        self._critical("set", lambda: self._client.set(key, value, ex=ttl))

    def exists(self, key: str) -> bool:
        return bool(self._critical("exists", lambda: self._client.exists(key)))

    def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(self._critical("delete", lambda: self._client.delete(*keys)))

    def pop(self, key: str) -> str | None:
        """
        Atomically reads and deletes a key (MULTI/EXEC). Used to consume a
        refresh token exactly once, so two concurrent /refresh calls with
        the same token cannot both succeed.
        """

        def run() -> str | None:
            pipe = self._client.pipeline(transaction=True)
            pipe.get(key)
            pipe.delete(key)
            value, _deleted = pipe.execute()
            return value

        return self._critical("pop", run)

    # ------------------------------------------------------------------

    def _critical(self, operation: str, func):
        try:
            return func()
        except REDIS_FAILURES as exc:
            self._record_failure(operation, exc)
            raise RedisUnavailableError(f"Redis unavailable during '{operation}'.") from exc

    def _cache_suspended(self) -> bool:
        if self._cache_cooldown_seconds and time.monotonic() < self._cache_suspended_until:
            self.metrics.incr("cache_skipped")
            return True
        return False

    def _record_cache_failure(self, operation: str, exc: BaseException) -> None:
        self._record_failure(operation, exc)
        if self._cache_cooldown_seconds:
            self._cache_suspended_until = time.monotonic() + self._cache_cooldown_seconds

    def _record_failure(self, operation: str, exc: BaseException) -> None:
        self.metrics.incr("redis_error")
        # Only the exception type: redis-py messages can include host/port.
        logger.warning("Redis operation '%s' failed (%s)", operation, type(exc).__name__)
