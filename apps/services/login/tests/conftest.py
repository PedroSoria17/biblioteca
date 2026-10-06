"""
Fixtures for the JWT + Redis flow tests.

No real PostgreSQL or Redis is used: users live in an in-memory dict that
replaces the repository functions, and Redis is an in-memory fake whose
MULTI/EXEC pipeline is atomic (guarded by a lock), like the real server.
"""

from __future__ import annotations

from contextlib import nullcontext
import fnmatch
import threading
import time

import bcrypt
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.redis_client import RedisGateway


JWT_SECRET = "login-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "redis-test-password"
USER_PASSWORD = "PasswordSeguro123!"


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float | None]] = {}
        self.ttls: dict[str, int] = {}
        self.down = False
        # When set, the N-th successful SET (1-based) fails: simulates Redis
        # dying halfway through a multi-step operation.
        self.fail_on_set_number: int | None = None
        self._set_calls = 0
        self.lock = threading.RLock()

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError(f"Error 10061 connecting to :{REDIS_PASSWORD}@10.0.0.9:6379")

    def _alive(self, key: str) -> bool:
        item = self.store.get(key)
        if item is None:
            return False
        if item[1] is not None and item[1] <= time.time():
            del self.store[key]
            return False
        return True

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        with self.lock:
            return self.store[key][0] if self._alive(key) else None

    def set(self, key, value, ex=None):
        self._check()
        with self.lock:
            self._set_calls += 1
            if self.fail_on_set_number == self._set_calls:
                raise RedisConnectionError("connection lost")
            self.store[key] = (value, time.time() + ex if ex else None)
            self.ttls[key] = ex
            return True

    def exists(self, *keys):
        self._check()
        with self.lock:
            return sum(1 for k in keys if self._alive(k))

    def delete(self, *keys):
        self._check()
        with self.lock:
            removed = 0
            for k in keys:
                if self._alive(k):
                    del self.store[k]
                    removed += 1
            return removed

    def scan_iter(self, match="*", count=None):
        self._check()
        with self.lock:
            return [k for k in list(self.store) if fnmatch.fnmatchcase(k, match) and self._alive(k)]

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def keys_with_prefix(self, prefix: str) -> list[str]:
        with self.lock:
            return [k for k in self.store if k.startswith(prefix) and self._alive(k)]


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list = []

    def get(self, key):
        self._ops.append(lambda: self._redis.get(key))

    def delete(self, key):
        self._ops.append(lambda: self._redis.delete(key))

    def execute(self):
        self._redis._check()
        with self._redis.lock:  # MULTI/EXEC: nothing interleaves
            return [op() for op in self._ops]


class FakeConnection:
    """Enough of a psycopg connection for `SELECT 1` in /health."""

    def cursor(self):
        return nullcontext(self)

    def execute(self, _sql):
        return None

    def fetchone(self):
        return (1,)


class FakeUserDb:
    """In-memory replacement for the usuarios rows the login flow reads."""

    def __init__(self) -> None:
        self.users: dict[int, dict] = {}
        self.down = False

    def add(self, usuario_id: int, email: str, role_id: int = 1, activo: bool = True) -> dict:
        user = {
            "usuario_id": usuario_id,
            "nombre_completo": f"User {usuario_id}",
            "email": email,
            # Low cost: only to keep the tests fast.
            "password_hash": bcrypt.hashpw(USER_PASSWORD.encode(), bcrypt.gensalt(4)).decode(),
            "es_administrador": role_id == 2,
            "role_id": role_id,
            "activo": activo,
        }
        self.users[usuario_id] = user
        return user

    def open_connection(self):
        if self.down:
            raise OSError("connection refused")
        return nullcontext(FakeConnection())

    def get_user_by_email(self, _conn, email):
        return next((dict(u) for u in self.users.values() if u["email"] == email), None)

    def get_user_by_id(self, _conn, usuario_id):
        user = self.users.get(usuario_id)
        return dict(user) if user else None


@pytest.fixture
def env(monkeypatch):
    values = {
        "SECRET_KEY": "flask-secret-for-tests",
        "DB_HOST": "127.0.0.1",
        "DB_NAME": "library_db",
        "DB_USER": "library_user",
        "DB_PASSWORD": "db-test-password",
        "JWT_SECRET_KEY": JWT_SECRET,
        "JWT_ACCESS_TTL_MINUTES": "20",
        "JWT_REFRESH_TTL_DAYS": "7",
        "REDIS_URL": f"redis://:{REDIS_PASSWORD}@127.0.0.1:6379/0",
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
        "APP_ENV": "development",
        "MAIL_ENABLED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def user_db(monkeypatch) -> FakeUserDb:
    from repositories import user_repository
    from routes import health
    from services import auth_service

    db = FakeUserDb()
    db.add(1, "admin@example.com", role_id=2)
    db.add(2, "user@example.com", role_id=1)
    db.add(3, "inactive@example.com", role_id=1, activo=False)

    monkeypatch.setattr(auth_service, "open_connection", db.open_connection)
    monkeypatch.setattr(health, "open_connection", db.open_connection)
    monkeypatch.setattr(user_repository, "get_user_by_email", db.get_user_by_email)
    monkeypatch.setattr(user_repository, "get_user_by_id", db.get_user_by_id)
    return db


@pytest.fixture
def app(env, fake_redis, user_db):
    from app import create_app

    application = create_app(redis_gateway=RedisGateway(fake_redis))
    application.testing = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
