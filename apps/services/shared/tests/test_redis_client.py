import logging

import pytest

from library_shared.errors import RedisUnavailableError
from library_shared.redis_client import RedisGateway, create_redis_client, require_ttl, ttl_until
from library_shared.settings import RedisSettings


def test_ping_and_health_when_redis_is_up(gateway):
    assert gateway.ping() is True
    assert gateway.health()["status"] == "up"


def test_ping_and_health_when_redis_is_down(broken_gateway):
    assert broken_gateway.ping() is False
    assert broken_gateway.health() == {"status": "down"}
    assert broken_gateway.metrics.get("redis_error") == 2


def test_cache_set_requires_explicit_positive_ttl(gateway, fake_redis):
    assert gateway.cache_set("books:1", "{}", 30) is True
    assert fake_redis.ttls["books:1"] == 30

    with pytest.raises(ValueError):
        gateway.cache_set("books:1", "{}", 0)


def test_cache_hit_and_miss_metrics(gateway):
    assert gateway.cache_get("books:missing") is None
    gateway.cache_set("books:1", "x", 30)
    assert gateway.cache_get("books:1") == "x"

    assert gateway.metrics.get("cache_miss") == 1
    assert gateway.metrics.get("cache_hit") == 1


def test_optional_operations_never_raise_when_redis_is_down(broken_gateway):
    assert broken_gateway.cache_get("books:1") is None
    assert broken_gateway.cache_set("books:1", "x", 30) is False
    assert broken_gateway.cache_delete("books:1") == 0
    assert broken_gateway.cache_delete_pattern("books:list:*") == 0
    assert broken_gateway.metrics.get("redis_error") == 4


@pytest.mark.parametrize(
    "call",
    [
        lambda g: g.get("k"),
        lambda g: g.set("k", "v", 10),
        lambda g: g.exists("k"),
        lambda g: g.delete("k"),
        lambda g: g.pop("k"),
    ],
)
def test_critical_operations_raise_when_redis_is_down(broken_gateway, call):
    with pytest.raises(RedisUnavailableError):
        call(broken_gateway)


def test_failure_logs_do_not_contain_connection_details(broken_gateway, caplog):
    with caplog.at_level(logging.WARNING, logger="library_shared.redis"):
        broken_gateway.cache_get("books:1")

    assert "ConnectionError" in caplog.text
    assert "secret-host" not in caplog.text


def test_cache_delete_pattern_only_removes_matching_keys(gateway, fake_redis):
    gateway.cache_set("books:list:all", "a", 30)
    gateway.cache_set("books:list:titulo=x", "b", 30)
    gateway.cache_set("books:9780000000001", "c", 30)

    assert gateway.cache_delete_pattern("books:list:*") == 2
    assert list(fake_redis.store) == ["books:9780000000001"]


def test_pop_reads_and_deletes_once(gateway):
    gateway.set("auth:refresh:j1", "data", 60)

    assert gateway.pop("auth:refresh:j1") == "data"
    assert gateway.pop("auth:refresh:j1") is None


def test_ttl_helpers():
    assert require_ttl(1.2) == 2
    with pytest.raises(ValueError):
        require_ttl(-5)
    assert ttl_until(1000, now=900) == 100
    # Already expired still yields a valid (minimal) TTL.
    assert ttl_until(1000, now=2000) == 1


def test_client_is_built_from_url_with_timeouts_and_without_connecting():
    settings = RedisSettings(
        url="redis://:s3cr3t@127.0.0.1:6399/2",
        connect_timeout_seconds=1.5,
        socket_timeout_seconds=2.5,
        health_check_interval_seconds=30,
    )

    client = create_redis_client(settings)
    kwargs = client.connection_pool.connection_kwargs

    assert kwargs["password"] == "s3cr3t"
    assert kwargs["db"] == 2
    assert kwargs["socket_connect_timeout"] == 1.5
    assert kwargs["socket_timeout"] == 2.5
    assert "s3cr3t" not in repr(settings)


def test_gateway_against_unreachable_real_client_fails_fast():
    # Real redis-py client pointed at a closed local port: proves timeouts
    # and exception mapping work without needing a Redis server.
    settings = RedisSettings(
        url="redis://:pw@127.0.0.1:1/0",
        connect_timeout_seconds=0.5,
        socket_timeout_seconds=0.5,
        health_check_interval_seconds=30,
    )
    gateway = RedisGateway.from_settings(settings)

    assert gateway.ping() is False
    assert gateway.cache_get("books:1") is None
    with pytest.raises(RedisUnavailableError):
        gateway.exists("jwt:revoked:x")


# --- cache cooldown (opt-in) and cache_invalidate --------------------------

class _FlakyRedis:
    """Counts calls; fails while `down` is True."""

    def __init__(self):
        self.calls = 0
        self.down = True
        self.data = {}

    def _maybe_fail(self):
        self.calls += 1
        if self.down:
            from redis.exceptions import TimeoutError as RedisTimeoutError

            raise RedisTimeoutError("Timeout connecting to server")

    def get(self, key):
        self._maybe_fail()
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self._maybe_fail()
        self.data[key] = value

    def delete(self, *keys):
        self._maybe_fail()
        return sum(1 for k in keys if self.data.pop(k, None) is not None)

    def scan_iter(self, match="*", count=None):
        self._maybe_fail()
        prefix = match.rstrip("*")
        return [k for k in list(self.data) if k.startswith(prefix)]

    def exists(self, *keys):
        self._maybe_fail()
        return sum(1 for k in keys if k in self.data)

    def ping(self):
        self._maybe_fail()
        return True


def test_cooldown_is_disabled_by_default():
    redis = _FlakyRedis()
    gateway = RedisGateway(redis)

    gateway.cache_get("a")
    gateway.cache_get("a")

    assert redis.calls == 2


def test_cooldown_skips_cache_reads_and_writes_after_a_failure():
    redis = _FlakyRedis()
    gateway = RedisGateway(redis, cache_cooldown_seconds=60)

    assert gateway.cache_get("a") is None   # real attempt, fails
    assert gateway.cache_set("a", "1", 10) is False  # skipped
    assert gateway.cache_get("a") is None   # skipped

    assert redis.calls == 1
    assert gateway.metrics.get("cache_skipped") == 2


def test_cooldown_never_skips_critical_operations():
    redis = _FlakyRedis()
    gateway = RedisGateway(redis, cache_cooldown_seconds=60)
    gateway.cache_get("a")

    with pytest.raises(RedisUnavailableError):
        gateway.exists("jwt:revoked:x")

    assert redis.calls == 2


def test_successful_ping_ends_the_cooldown():
    redis = _FlakyRedis()
    gateway = RedisGateway(redis, cache_cooldown_seconds=60)
    gateway.cache_get("a")
    redis.down = False

    assert gateway.ping() is True
    assert gateway.cache_set("a", "1", 10) is True


def test_cache_invalidate_deletes_keys_and_patterns(gateway, fake_redis):
    gateway.cache_set("books:1", "x", 30)
    gateway.cache_set("books:list:all", "x", 30)
    gateway.cache_set("books:list:q=a", "x", 30)
    gateway.cache_set("books:2", "x", 30)

    assert gateway.cache_invalidate(keys=("books:1",), patterns=("books:list:*",)) is True

    assert list(fake_redis.store) == ["books:2"]
    assert gateway.metrics.get("cache_invalidation") == 1


def test_cache_invalidate_reports_failure_without_raising_and_ignores_cooldown():
    redis = _FlakyRedis()
    gateway = RedisGateway(redis, cache_cooldown_seconds=60)
    gateway.cache_get("a")  # starts the cooldown

    assert gateway.cache_invalidate(keys=("books:1",), patterns=("books:list:*",)) is False

    assert redis.calls == 3  # get + delete + scan: invalidation still attempted
    assert gateway.metrics.get("cache_invalidation_failed") == 1
