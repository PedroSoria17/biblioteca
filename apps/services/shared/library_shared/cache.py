"""
Read-through JSON cache on top of the OPTIONAL Redis operations.

PostgreSQL remains the source of truth: if Redis is down, slow or holds a
corrupt entry, the loader is called and its result is returned as usual.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from library_shared.redis_client import RedisGateway


logger = logging.getLogger("library_shared.cache")


def cached_json(
    gateway: RedisGateway | None,
    key: str,
    ttl_seconds: int,
    loader: Callable[[], Any],
) -> Any:
    """
    Returns the cached value for `key` or calls `loader()` and caches it.
    The loaded value must be JSON-serializable (convert Decimal/datetime
    before returning it from the loader).
    """
    if gateway is not None:
        cached = gateway.cache_get(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except ValueError:
                logger.warning("Discarding unreadable cache entry")
                gateway.cache_delete(key)

    value = loader()

    if gateway is not None:
        gateway.cache_set(key, json.dumps(value), ttl_seconds)

    return value
