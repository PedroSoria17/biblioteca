from __future__ import annotations

import fnmatch
import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.redis_client import RedisGateway
from library_shared.settings import JwtSettings


TEST_SECRET = "unit-test-secret-key-that-is-long-enough-0123456789"


class FakeRedis:
    """In-memory stand-in for the subset of redis.Redis the gateway uses."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float | None]] = {}
        self.ttls: dict[str, int] = {}

    def _alive(self, key: str) -> bool:
        item = self.store.get(key)
        if item is None:
            return False
        if item[1] is not None and item[1] <= time.time():
            del self.store[key]
            return False
        return True

    def ping(self) -> bool:
        return True

    def get(self, key):
        return self.store[key][0] if self._alive(key) else None

    def set(self, key, value, ex=None):
        self.store[key] = (value, time.time() + ex if ex else None)
        self.ttls[key] = ex
        return True

    def exists(self, *keys):
        return sum(1 for k in keys if self._alive(k))

    def delete(self, *keys):
        removed = 0
        for k in keys:
            if self._alive(k):
                del self.store[k]
                removed += 1
        return removed

    def scan_iter(self, match="*", count=None):
        return [k for k in list(self.store) if fnmatch.fnmatchcase(k, match) and self._alive(k)]

    def pipeline(self, transaction=True):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list = []

    def get(self, key):
        self._ops.append(lambda: self._redis.get(key))

    def delete(self, key):
        self._ops.append(lambda: self._redis.delete(key))

    def execute(self):
        return [op() for op in self._ops]


class BrokenRedis:
    """Every call fails as if Redis were down / unreachable."""

    def __getattr__(self, name):
        def fail(*_args, **_kwargs):
            raise RedisConnectionError("Error 10061 connecting to secret-host:6379")

        return fail


@pytest.fixture
def jwt_settings() -> JwtSettings:
    return JwtSettings(secret_key=TEST_SECRET, access_ttl_seconds=20 * 60, refresh_ttl_seconds=7 * 24 * 3600)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def gateway(fake_redis) -> RedisGateway:
    return RedisGateway(fake_redis)


@pytest.fixture
def broken_gateway() -> RedisGateway:
    return RedisGateway(BrokenRedis())
