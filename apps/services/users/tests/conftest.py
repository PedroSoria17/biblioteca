"""
Fixtures for the users microservice tests.

No real PostgreSQL or Redis is used here:
- Redis is an in-memory fake (only what JWT revocation needs) that can be
  switched "down" to simulate an outage.
- The repository functions are replaced by FakeUserDb, which reproduces the
  database rules the service relies on: UNIQUE email,
  ux_usuarios_un_solo_administrador, fk_usuarios_role,
  fk_pedidos_usuario (RESTRICT), the role_id -> es_administrador trigger,
  and transaction rollback on any exception.

tests/test_integration_postgres.py runs the same flows against a REAL
disposable PostgreSQL when USERS_IT_DB_NAME is set.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import bcrypt
import psycopg
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.redis_client import RedisGateway
from library_shared.settings import load_jwt_settings


JWT_SECRET = "users-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "redis-test-password"
DB_PASSWORD = "db-test-password"
USER_PASSWORD = "PasswordSeguro123!"

ADMIN_ID = 1
USER_ID = 2
INACTIVE_ID = 3


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError(f"Error 10061 connecting to :{REDIS_PASSWORD}@10.0.0.9:6379")

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self._check()
        assert ex, "every Redis write must carry a TTL"
        self.store[key] = value
        return True

    def exists(self, *keys):
        self._check()
        return sum(1 for k in keys if k in self.store)

    def delete(self, *keys):
        self._check()
        return sum(1 for k in keys if self.store.pop(k, None) is not None)


# ---------------------------------------------------------------------------
# PostgreSQL (repository layer)
# ---------------------------------------------------------------------------

class _ConstraintError:
    """psycopg errors built by hand have no diag; give them the constraint."""

    def __init__(self, message: str, constraint_name: str) -> None:
        super().__init__(message)
        self._constraint = constraint_name

    @property
    def diag(self):  # noqa: D401 - mimics psycopg.Error.diag
        return SimpleNamespace(constraint_name=self._constraint)


class FakeUniqueViolation(_ConstraintError, psycopg.errors.UniqueViolation):
    pass


class FakeForeignKeyViolation(_ConstraintError, psycopg.errors.ForeignKeyViolation):
    pass


class FakeConnection:
    """Enough of a psycopg connection for `SELECT 1` in /health."""

    def cursor(self):
        return nullcontext(self)

    def execute(self, _sql):
        return None

    def fetchone(self):
        return (1,)


PUBLIC_FIELDS = ("usuario_id", "nombre_completo", "email", "role_id", "activo", "fecha_registro")


class FakeUserDb:
    def __init__(self) -> None:
        self.users: dict[int, dict] = {}
        self.roles = {1: "USER", 2: "ADMIN"}
        self.orders: dict[int, int] = {}  # usuario_id -> number of pedidos
        self.next_id = 1
        self.down = False
        self.commits = 0
        self.rollbacks = 0

    # -- seed helpers -------------------------------------------------------

    def add(self, email: str, role_id: int = 1, activo: bool = True, password: str = USER_PASSWORD) -> dict:
        usuario_id = self.next_id
        self.next_id += 1
        row = {
            "usuario_id": usuario_id,
            "nombre_completo": f"User {usuario_id}",
            "email": email,
            # Low cost: only to keep the tests fast.
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode(),
            "role_id": role_id,
            "es_administrador": role_id == 2,
            "activo": activo,
            "fecha_registro": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        self._check_constraints(row)
        self.users[usuario_id] = row
        return row

    # -- connection / transaction -------------------------------------------

    def open_connection(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        return nullcontext(FakeConnection())

    @contextmanager
    def transaction(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        snapshot = (copy.deepcopy(self.users), dict(self.orders), self.next_id)
        try:
            yield FakeConnection()
        except BaseException:
            self.users, self.orders, self.next_id = snapshot
            self.rollbacks += 1
            raise
        self.commits += 1

    # -- constraints / trigger ----------------------------------------------

    def _check_constraints(self, row: dict) -> None:
        for other in self.users.values():
            if other["usuario_id"] == row["usuario_id"]:
                continue
            if other["email"] == row["email"]:  # UNIQUE is case-sensitive
                raise FakeUniqueViolation("duplicate key", "usuarios_email_key")
            if other["es_administrador"] and row["es_administrador"]:
                raise FakeUniqueViolation("duplicate key", "ux_usuarios_un_solo_administrador")
        if row["role_id"] not in self.roles:
            raise FakeForeignKeyViolation("fk violation", "fk_usuarios_role")
        assert row["es_administrador"] == (row["role_id"] == 2)  # ck_usuarios_role_admin_sync

    @staticmethod
    def public(row: dict | None) -> dict | None:
        if row is None:
            return None
        result = {k: row[k] for k in PUBLIC_FIELDS}
        result["role"] = {1: "USER", 2: "ADMIN"}.get(row["role_id"])
        return result

    # -- repository API (same signatures as repositories.user_repository) ----

    def list_users(self, _conn, limit, offset):
        rows = [self.users[k] for k in sorted(self.users)]
        return [self.public(r) for r in rows[offset : offset + limit]]

    def count_users(self, _conn):
        return len(self.users)

    def get_user(self, _conn, usuario_id, for_update=False):
        return self.public(self.users.get(usuario_id))

    def email_taken(self, _conn, email, exclude_usuario_id=None):
        return any(
            u["email"].lower() == email.lower() and u["usuario_id"] != exclude_usuario_id
            for u in self.users.values()
        )

    def role_exists(self, _conn, role_id):
        return role_id in self.roles

    def admin_exists(self, _conn, exclude_usuario_id=None):
        return any(u["role_id"] == 2 and u["usuario_id"] != exclude_usuario_id for u in self.users.values())

    def count_other_active_admins(self, _conn, usuario_id):
        return sum(
            1 for u in self.users.values() if u["role_id"] == 2 and u["activo"] and u["usuario_id"] != usuario_id
        )

    def insert_user(self, _conn, nombre_completo, email, password_hash, role_id, activo):
        row = {
            "usuario_id": self.next_id,
            "nombre_completo": nombre_completo,
            "email": email,
            "password_hash": password_hash,
            "role_id": role_id,
            "es_administrador": role_id == 2,  # trigger on INSERT
            "activo": activo,
            "fecha_registro": datetime.now(timezone.utc),
        }
        self._check_constraints(row)
        self.next_id += 1
        self.users[row["usuario_id"]] = row
        return row["usuario_id"]

    def update_user(self, _conn, usuario_id, changes):
        assert "es_administrador" not in changes, "es_administrador must be derived by the trigger"
        row = dict(self.users[usuario_id])
        row.update(changes)
        if "role_id" in changes:
            row["es_administrador"] = row["role_id"] == 2  # trigger on UPDATE OF role_id
        self._check_constraints(row)
        self.users[usuario_id] = row

    def has_orders(self, _conn, usuario_id):
        return self.orders.get(usuario_id, 0) > 0

    def delete_user(self, _conn, usuario_id):
        if self.orders.get(usuario_id, 0) > 0:
            raise FakeForeignKeyViolation("fk violation", "fk_pedidos_usuario")
        self.users.pop(usuario_id, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env(monkeypatch):
    values = {
        "DB_HOST": "127.0.0.1",
        "DB_NAME": "library_db",
        "DB_USER": "library_user",
        "DB_PASSWORD": DB_PASSWORD,
        "JWT_SECRET_KEY": JWT_SECRET,
        "JWT_ACCESS_TTL_MINUTES": "20",
        "JWT_REFRESH_TTL_DAYS": "7",
        "REDIS_URL": f"redis://:{REDIS_PASSWORD}@127.0.0.1:6379/0",
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
        "APP_ENV": "development",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def jwt_settings(env):
    return load_jwt_settings(env)


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def gateway(fake_redis) -> RedisGateway:
    return RedisGateway(fake_redis)


@pytest.fixture
def user_db(monkeypatch) -> FakeUserDb:
    from repositories import user_repository
    from routes import health
    from services import passwords, user_service

    db = FakeUserDb()
    db.add("admin@example.com", role_id=2)  # usuario_id 1
    db.add("user@example.com", role_id=1)  # usuario_id 2
    db.add("inactive@example.com", role_id=1, activo=False)  # usuario_id 3

    monkeypatch.setattr(user_service, "open_connection", db.open_connection)
    monkeypatch.setattr(user_service, "transaction", db.transaction)
    monkeypatch.setattr(health, "open_connection", db.open_connection)
    for name in (
        "list_users",
        "count_users",
        "get_user",
        "email_taken",
        "role_exists",
        "admin_exists",
        "count_other_active_admins",
        "insert_user",
        "update_user",
        "has_orders",
        "delete_user",
    ):
        monkeypatch.setattr(user_repository, name, getattr(db, name))
    # Same algorithm, lower cost: keeps the suite fast. The real cost (12)
    # is checked in test_passwords.py.
    monkeypatch.setattr(passwords, "BCRYPT_ROUNDS", 4)
    return db


@pytest.fixture
def app(env, gateway, user_db):
    from app import create_app

    application = create_app(redis_gateway=gateway)
    application.testing = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_token(jwt_settings):
    def _make(user_id: int, role_id: int, *, now: int | None = None, refresh: bool = False):
        factory = create_refresh_token if refresh else create_access_token
        return factory(jwt_settings, user_id, role_id, now=now)

    return _make


def bearer(issued) -> dict:
    token = issued if isinstance(issued, str) else issued.token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(make_token):
    return bearer(make_token(ADMIN_ID, 2))


@pytest.fixture
def user_headers(make_token):
    return bearer(make_token(USER_ID, 1))
