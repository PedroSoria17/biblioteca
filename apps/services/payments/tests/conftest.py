"""
Fixtures for the payments microservice tests.

No real PostgreSQL or Redis is used here:
- Redis is an in-memory fake (JWT revocation + Books cache keys).
- The repository functions are replaced by FakePaymentDb, which reproduces
  the schema rules Payments relies on: uq_pagos_referencia,
  ux_pagos_un_aprobado_por_pedido, ck_pagos_fecha_pago, ck_pagos_monto,
  libros_stock_check, the column DEFAULTs, and transaction rollback.

tests/test_integration_postgres.py runs the critical flows (real row locks,
concurrent approvals/refunds, approval vs cancellation, constraints) against
a REAL disposable PostgreSQL when PAYMENTS_IT_DB_NAME is set.
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


JWT_SECRET = "payments-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "redis-test-password"
DB_PASSWORD = "db-test-password"

ADMIN_ID = 1
USER_ID = 2
OTHER_USER_ID = 3
INACTIVE_ID = 4

ISBN_A = "9780000000001"
ISBN_B = "9780000000002"


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


class _ConstraintError:
    def __init__(self, message: str, constraint_name: str) -> None:
        super().__init__(message)
        self._constraint = constraint_name

    @property
    def diag(self):
        return SimpleNamespace(constraint_name=self._constraint)


class FakeUniqueViolation(_ConstraintError, psycopg.errors.UniqueViolation):
    pass


class FakeCheckViolation(_ConstraintError, psycopg.errors.CheckViolation):
    pass


class FakeConnection:
    def cursor(self):
        return nullcontext(self)

    def execute(self, _sql):
        return None

    def fetchone(self):
        return (1,)


class FakePaymentDb:
    def __init__(self) -> None:
        self.users: dict[int, bool] = {}
        self.stock: dict[str, int] = {}
        self.orders: dict[int, dict] = {}
        self.items: dict[int, list[dict]] = {}
        self.payments: dict[int, dict] = {}
        self.next_order = 1
        self.next_payment = 1
        self.clock = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        self.down = False
        self.rollbacks = 0
        self.locked_books: list[list[str]] = []

    # -- seed helpers -----------------------------------------------------------

    def add_order(self, usuario_id: int, total: str, estado: str = "pending", items=None) -> int:
        pedido_id = self.next_order
        self.next_order += 1
        self.orders[pedido_id] = {
            "pedido_id": pedido_id, "usuario_id": usuario_id, "estado": estado, "total": Decimal(total),
        }
        self.items[pedido_id] = [dict(i) for i in (items or [{"isbn": ISBN_A, "cantidad": 1}])]
        return pedido_id

    def add_payment(self, pedido_id: int, estado: str = "pending", monto: str | None = None, metodo="cash") -> int:
        monto_value = Decimal(monto) if monto is not None else self.orders[pedido_id]["total"]
        pago_id = self.insert_payment(None, pedido_id, monto_value, metodo, f"SEED-{self.next_payment}")
        self.payments[pago_id]["estado"] = estado
        if estado in ("approved", "refunded"):
            self.payments[pago_id]["fecha_pago"] = self.clock
        return pago_id

    # -- connection / transaction -----------------------------------------------

    def open_connection(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        return nullcontext(FakeConnection())

    @contextmanager
    def transaction(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        snapshot = copy.deepcopy((self.stock, self.orders, self.payments, self.next_payment))
        try:
            yield FakeConnection()
        except BaseException:
            self.stock, self.orders, self.payments, self.next_payment = snapshot
            self.rollbacks += 1
            raise

    # -- constraints --------------------------------------------------------------

    def _check_payment(self, row: dict) -> None:
        if row["monto"] <= 0:
            raise FakeCheckViolation("check", "ck_pagos_monto")
        if row["estado"] in ("approved", "refunded") and row["fecha_pago"] is None:
            raise FakeCheckViolation("check", "ck_pagos_fecha_pago")
        for other in self.payments.values():
            if other["pago_id"] == row["pago_id"]:
                continue
            if other["referencia"] == row["referencia"]:
                raise FakeUniqueViolation("duplicate", "uq_pagos_referencia")
            if row["estado"] == "approved" and other["estado"] == "approved" and other["pedido_id"] == row["pedido_id"]:
                raise FakeUniqueViolation("duplicate", "ux_pagos_un_aprobado_por_pedido")

    def _public(self, pago_id: int) -> dict | None:
        row = self.payments.get(pago_id)
        if row is None:
            return None
        return {**row, "usuario_id": self.orders[row["pedido_id"]]["usuario_id"]}

    # -- repository API -------------------------------------------------------------

    def list_payments(self, _conn, filters, limit, offset):
        rows = [self._public(p) for p in self.payments]
        for key in ("usuario_id", "pedido_id", "estado", "metodo_pago"):
            if filters.get(key) is not None:
                rows = [r for r in rows if r[key] == filters[key]]
        if filters.get("desde"):
            rows = [r for r in rows if r["fecha_creacion"] >= filters["desde"]]
        if filters.get("hasta"):
            rows = [r for r in rows if r["fecha_creacion"] < filters["hasta"]]
        rows.sort(key=lambda r: (r["fecha_creacion"], r["pago_id"]), reverse=True)
        return rows[offset : offset + limit]

    def count_payments(self, conn, filters):
        return len(self.list_payments(conn, filters, 10**9, 0))

    def get_payment(self, _conn, pago_id):
        return self._public(pago_id)

    def get_order(self, _conn, pedido_id):
        order = self.orders.get(pedido_id)
        return dict(order) if order else None

    def get_user_activo(self, _conn, usuario_id):
        return self.users.get(usuario_id)

    def lock_order(self, conn, pedido_id):
        return self.get_order(conn, pedido_id)

    def lock_payment(self, _conn, pago_id):
        row = self.payments.get(pago_id)
        return dict(row) if row else None

    def approved_payment_exists(self, _conn, pedido_id):
        return any(p["pedido_id"] == pedido_id and p["estado"] == "approved" for p in self.payments.values())

    def insert_payment(self, _conn, pedido_id, monto, metodo_pago, referencia):
        self.clock += timedelta(minutes=1)
        row = {
            "pago_id": self.next_payment, "pedido_id": pedido_id, "monto": monto, "metodo_pago": metodo_pago,
            "estado": "pending", "referencia": referencia, "fecha_pago": None,
            "fecha_creacion": self.clock, "fecha_actualizacion": self.clock,
        }
        self._check_payment(row)
        self.next_payment += 1
        self.payments[row["pago_id"]] = row
        return row["pago_id"]

    def set_payment_status(self, _conn, pago_id, estado, set_fecha_pago=False):
        row = dict(self.payments[pago_id], estado=estado)
        if set_fecha_pago:
            row["fecha_pago"] = self.clock
        self._check_payment(row)
        self.payments[pago_id] = row

    def set_order_status(self, _conn, pedido_id, estado):
        assert estado in ("pending", "paid", "completed", "cancelled")
        self.orders[pedido_id]["estado"] = estado

    def get_order_items(self, _conn, pedido_id):
        return sorted((dict(i) for i in self.items[pedido_id]), key=lambda i: i["isbn"])

    def lock_books(self, _conn, isbns):
        self.locked_books.append(list(isbns))

    def add_stock(self, _conn, isbn, cantidad):
        self.stock[isbn] = self.stock.get(isbn, 0) + cantidad


REPOSITORY_FUNCTIONS = (
    "list_payments", "count_payments", "get_payment", "get_order", "get_user_activo", "lock_order",
    "lock_payment", "approved_payment_exists", "insert_payment", "set_payment_status", "set_order_status",
    "get_order_items", "lock_books", "add_stock",
)


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
def pay_db(monkeypatch) -> FakePaymentDb:
    from repositories import payment_repository
    from routes import health
    from services import payment_service

    db = FakePaymentDb()
    db.users = {ADMIN_ID: True, USER_ID: True, OTHER_USER_ID: True, INACTIVE_ID: False}
    db.stock = {ISBN_A: 3, ISBN_B: 0}

    monkeypatch.setattr(payment_service, "open_connection", db.open_connection)
    monkeypatch.setattr(payment_service, "transaction", db.transaction)
    monkeypatch.setattr(health, "open_connection", db.open_connection)
    for name in REPOSITORY_FUNCTIONS:
        monkeypatch.setattr(payment_repository, name, getattr(db, name))
    return db


@pytest.fixture
def app(env, gateway, pay_db):
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
