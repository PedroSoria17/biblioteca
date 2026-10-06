"""
Fixtures for the orders microservice tests.

No real PostgreSQL or Redis is used here:
- Redis is an in-memory fake (JWT revocation + Books cache keys) that can
  be switched "down".
- The repository functions are replaced by FakeOrderDb, which reproduces
  the schema rules the service relies on: libros_stock_check (stock >= 0),
  pedido_detalle PRIMARY KEY (pedido_id, isbn), subtotal GENERATED, the
  total trigger, the 'pending' DEFAULT, and transaction rollback on any
  exception.

tests/test_integration_postgres.py runs the critical flows (atomicity,
real row locks, concurrency, trigger, CHECKs) against a REAL disposable
PostgreSQL when ORDERS_IT_DB_NAME is set.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import fnmatch
from types import SimpleNamespace

import psycopg
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.redis_client import RedisGateway
from library_shared.settings import load_jwt_settings


JWT_SECRET = "orders-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "redis-test-password"
DB_PASSWORD = "db-test-password"

ADMIN_ID = 1
USER_ID = 2
OTHER_USER_ID = 3
INACTIVE_ID = 4

ISBN_A = "9780000000001"  # precio 10.50, stock 5
ISBN_B = "9780000000002"  # precio 20.00, stock 1
ISBN_C = "9780000000003"  # precio 7.25, stock 0
ISBN_MISSING = "9789999999999"


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

    def scan_iter(self, match="*", count=None):
        self._check()
        return [k for k in list(self.store) if fnmatch.fnmatchcase(k, match)]


# ---------------------------------------------------------------------------
# PostgreSQL (repository layer)
# ---------------------------------------------------------------------------

class _ConstraintError:
    def __init__(self, message: str, constraint_name: str) -> None:
        super().__init__(message)
        self._constraint = constraint_name

    @property
    def diag(self):
        return SimpleNamespace(constraint_name=self._constraint)


class FakeCheckViolation(_ConstraintError, psycopg.errors.CheckViolation):
    pass


class FakeUniqueViolation(_ConstraintError, psycopg.errors.UniqueViolation):
    pass


class FakeConnection:
    def cursor(self):
        return nullcontext(self)

    def execute(self, _sql):
        return None

    def fetchone(self):
        return (1,)


class FakeOrderDb:
    def __init__(self) -> None:
        self.users: dict[int, bool] = {}  # usuario_id -> activo
        self.books: dict[str, dict] = {}
        self.orders: dict[int, dict] = {}
        self.items: dict[tuple[int, str], dict] = {}  # (pedido_id, isbn) -> {cantidad, precio_unitario}
        self.next_id = 1
        self.clock = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        self.down = False
        self.rollbacks = 0
        self.commits = 0
        self.locked: list[list[str]] = []  # isbn lists passed to lock_books, in call order

    def add_book(self, isbn: str, titulo: str, precio: str, stock: int) -> None:
        self.books[isbn] = {"isbn": isbn, "titulo": titulo, "precio": Decimal(precio), "stock": stock}

    def add_order(self, usuario_id: int, lines: dict[str, int], estado: str = "pending") -> int:
        """Seed helper (like a previously committed order)."""
        pedido_id = self.insert_order(None, usuario_id)
        for isbn, cantidad in lines.items():
            self.insert_item(None, pedido_id, isbn, cantidad, self.books[isbn]["precio"])
        self.orders[pedido_id]["estado"] = estado
        return pedido_id

    # -- connection / transaction -------------------------------------------

    def open_connection(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        return nullcontext(FakeConnection())

    @contextmanager
    def transaction(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        snapshot = copy.deepcopy((self.users, self.books, self.orders, self.items, self.next_id))
        try:
            yield FakeConnection()
        except BaseException:
            self.users, self.books, self.orders, self.items, self.next_id = snapshot
            self.rollbacks += 1
            raise
        self.commits += 1

    # -- helpers ------------------------------------------------------------

    def _order_row(self, pedido_id: int) -> dict:
        order = self.orders[pedido_id]
        count = sum(1 for (p, _i) in self.items if p == pedido_id)
        return {**order, "items_count": count}

    def _recalculate_total(self, pedido_id: int) -> None:  # trg_pedido_detalle_recalcular_total
        self.orders[pedido_id]["total"] = sum(
            (i["cantidad"] * i["precio_unitario"] for (p, _isbn), i in self.items.items() if p == pedido_id),
            Decimal("0"),
        )

    # -- repository API -------------------------------------------------------

    def list_orders(self, _conn, filters, limit, offset):
        rows = [self._order_row(p) for p in self.orders]
        if filters.get("usuario_id") is not None:
            rows = [r for r in rows if r["usuario_id"] == filters["usuario_id"]]
        if filters.get("estado"):
            rows = [r for r in rows if r["estado"] == filters["estado"]]
        if filters.get("desde"):
            rows = [r for r in rows if r["fecha_creacion"] >= filters["desde"]]
        if filters.get("hasta"):
            rows = [r for r in rows if r["fecha_creacion"] < filters["hasta"]]
        rows.sort(key=lambda r: (r["fecha_creacion"], r["pedido_id"]), reverse=True)
        return rows[offset : offset + limit]

    def count_orders(self, conn, filters):
        return len(self.list_orders(conn, filters, 10**9, 0))

    def get_order(self, _conn, pedido_id, for_update=False):
        return self._order_row(pedido_id) if pedido_id in self.orders else None

    def list_items(self, _conn, pedido_id):
        rows = [
            {
                "isbn": isbn,
                "titulo": self.books[isbn]["titulo"],
                "cantidad": i["cantidad"],
                "precio_unitario": i["precio_unitario"],
                "subtotal": i["cantidad"] * i["precio_unitario"],  # GENERATED
            }
            for (p, isbn), i in self.items.items()
            if p == pedido_id
        ]
        return sorted(rows, key=lambda r: r["isbn"])

    def get_user_activo(self, _conn, usuario_id):
        return self.users.get(usuario_id)

    def lock_books(self, _conn, isbns):
        self.locked.append(list(isbns))
        return {isbn: dict(self.books[isbn]) for isbn in sorted(isbns) if isbn in self.books}

    def insert_order(self, _conn, usuario_id):
        pedido_id = self.next_id
        self.next_id += 1
        self.clock += timedelta(minutes=1)
        self.orders[pedido_id] = {
            "pedido_id": pedido_id,
            "usuario_id": usuario_id,
            "estado": "pending",  # DEFAULT
            "total": Decimal("0"),  # DEFAULT
            "fecha_creacion": self.clock,
            "fecha_actualizacion": self.clock,
        }
        return pedido_id

    def insert_item(self, _conn, pedido_id, isbn, cantidad, precio_unitario):
        if (pedido_id, isbn) in self.items:
            raise FakeUniqueViolation("duplicate key", "pedido_detalle_pkey")
        self.items[(pedido_id, isbn)] = {"cantidad": cantidad, "precio_unitario": precio_unitario}
        self._recalculate_total(pedido_id)

    def change_stock(self, _conn, isbn, delta):
        new_stock = self.books[isbn]["stock"] + delta
        if new_stock < 0:
            raise FakeCheckViolation("check violation", "libros_stock_check")
        self.books[isbn]["stock"] = new_stock

    def set_status(self, _conn, pedido_id, estado):
        assert estado in ("pending", "paid", "completed", "cancelled")  # ck_pedidos_estado
        self.orders[pedido_id]["estado"] = estado

    def get_order_items_for_restock(self, _conn, pedido_id):
        return sorted(
            ({"isbn": isbn, "cantidad": i["cantidad"]} for (p, isbn), i in self.items.items() if p == pedido_id),
            key=lambda r: r["isbn"],
        )


REPOSITORY_FUNCTIONS = (
    "list_orders",
    "count_orders",
    "get_order",
    "list_items",
    "get_user_activo",
    "lock_books",
    "insert_order",
    "insert_item",
    "change_stock",
    "set_status",
    "get_order_items_for_restock",
)


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
def order_db(monkeypatch) -> FakeOrderDb:
    from repositories import order_repository
    from routes import health
    from services import order_service

    db = FakeOrderDb()
    db.users = {ADMIN_ID: True, USER_ID: True, OTHER_USER_ID: True, INACTIVE_ID: False}
    db.add_book(ISBN_A, "Libro A", "10.50", 5)
    db.add_book(ISBN_B, "Libro B", "20.00", 1)
    db.add_book(ISBN_C, "Libro C", "7.25", 0)

    monkeypatch.setattr(order_service, "open_connection", db.open_connection)
    monkeypatch.setattr(order_service, "transaction", db.transaction)
    monkeypatch.setattr(health, "open_connection", db.open_connection)
    for name in REPOSITORY_FUNCTIONS:
        monkeypatch.setattr(order_repository, name, getattr(db, name))
    return db


@pytest.fixture
def app(env, gateway, order_db):
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


@pytest.fixture
def other_headers(make_token):
    return bearer(make_token(OTHER_USER_ID, 1))


def order_body(*lines) -> dict:
    return {"items": [{"isbn": isbn, "cantidad": cantidad} for isbn, cantidad in lines]}
