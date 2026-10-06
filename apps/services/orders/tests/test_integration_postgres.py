"""
Integration tests against a REAL, DISPOSABLE PostgreSQL database.

Skipped unless ORDERS_IT_DB_NAME is set. The name MUST end in "_test"
(enforced below): never point them at library_db. They create and remove
only their own rows (users 'it.orders.*', books in IT_BOOKS and their
orders), but they do write pedidos / pedido_detalle / libros.

Verified for real: row locks (SELECT ... FOR UPDATE), concurrent buyers of
the last copy, deadlock-free multi-book orders, the total trigger, the
GENERATED subtotal, CHECKs, frozen prices, rollback of partial work and
idempotent cancellation under concurrency.

Redis is NOT real here (in-memory fake from conftest.py).

Environment:
  ORDERS_IT_DB_HOST (127.0.0.1), ORDERS_IT_DB_PORT (5432), ORDERS_IT_DB_NAME,
  ORDERS_IT_DB_USER (library_user), ORDERS_IT_DB_PASSWORD
"""

from __future__ import annotations

from decimal import Decimal
import os
import threading
import time

import pytest

from conftest import FakeRedis, bearer, order_body


IT_DB_NAME = os.getenv("ORDERS_IT_DB_NAME", "")

pytestmark = pytest.mark.skipif(not IT_DB_NAME, reason="ORDERS_IT_DB_NAME not set (no disposable PostgreSQL)")

# isbn -> (precio, stock)
IT_BOOKS = {
    "9792222222221": ("10.50", 5),
    "9792222222222": ("20.00", 1),  # the "last copy"
    "9792222222223": ("7.25", 50),
    "9792222222224": ("3.10", 50),
}
B1, B2, B3, B4 = sorted(IT_BOOKS)
MISSING = "9792222222229"


def _db_env() -> dict[str, str]:
    if not IT_DB_NAME.endswith("_test"):
        pytest.fail("ORDERS_IT_DB_NAME must end with '_test': these tests write and delete rows.")
    return {
        "DB_HOST": os.getenv("ORDERS_IT_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("ORDERS_IT_DB_PORT", "5432"),
        "DB_NAME": IT_DB_NAME,
        "DB_USER": os.getenv("ORDERS_IT_DB_USER", "library_user"),
        "DB_PASSWORD": os.getenv("ORDERS_IT_DB_PASSWORD", ""),
    }


@pytest.fixture
def db_env(env, monkeypatch):
    values = _db_env()
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def sql(db_env):
    import psycopg

    conn = psycopg.connect(
        host=db_env["DB_HOST"], port=db_env["DB_PORT"], dbname=db_env["DB_NAME"],
        user=db_env["DB_USER"], password=db_env["DB_PASSWORD"], autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def _all(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


IT_USERS = "SELECT usuario_id FROM usuarios WHERE email LIKE 'it.orders.%%'"


def _cleanup(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM pedido_detalle WHERE pedido_id IN (SELECT pedido_id FROM pedidos WHERE usuario_id IN ({IT_USERS}))")
        cur.execute(f"DELETE FROM pedidos WHERE usuario_id IN ({IT_USERS})")
        cur.execute("DELETE FROM libros WHERE isbn = ANY(%s)", (list(IT_BOOKS),))
        cur.execute("DELETE FROM usuarios WHERE email LIKE 'it.orders.%%'")


@pytest.fixture
def seed(sql):
    _cleanup(sql)
    formato_id = _one(sql, "SELECT min(formato_id) FROM formatos")[0]
    categoria_id = _one(sql, "SELECT min(categoria_id) FROM categorias")[0]
    for isbn, (precio, stock) in IT_BOOKS.items():
        _one(
            sql,
            "INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id) "
            "VALUES (%s, %s, 2000, %s, %s, %s, %s) RETURNING isbn",
            (isbn, f"IT {isbn[-1]}", precio, stock, formato_id, categoria_id),
        )

    def user(email, activo=True):
        return _one(
            sql,
            "INSERT INTO usuarios (nombre_completo, email, password_hash, activo) VALUES ('IT', %s, 'x', %s) "
            "RETURNING usuario_id",
            (email, activo),
        )[0]

    ids = {"u1": user("it.orders.u1@example.com"), "u2": user("it.orders.u2@example.com"),
           "inactive": user("it.orders.off@example.com", activo=False)}
    yield ids
    _cleanup(sql)


@pytest.fixture
def it_app(db_env, seed):
    from app import create_app
    from library_shared.redis_client import RedisGateway

    application = create_app(redis_gateway=RedisGateway(FakeRedis()))
    application.testing = True
    return application


@pytest.fixture
def it_client(it_app):
    return it_app.test_client()


@pytest.fixture
def h(make_token, seed):
    """Headers per actor: h['u1'], h['u2'], h['inactive'], h['admin'] (any id, role ADMIN)."""
    headers = {name: bearer(make_token(uid, 1)) for name, uid in seed.items()}
    headers["admin"] = bearer(make_token(seed["u2"], 2))
    return headers


def _stock(sql, isbn) -> int:
    return _one(sql, "SELECT stock FROM libros WHERE isbn = %s", (isbn,))[0]


def _orders_of(sql, usuario_id) -> int:
    return _one(sql, "SELECT count(*) FROM pedidos WHERE usuario_id = %s", (usuario_id,))[0]


@pytest.fixture
def slow_locks(monkeypatch):
    """Hold the book locks for a while so concurrent requests really overlap."""
    from repositories import order_repository

    real_lock = order_repository.lock_books
    events: list[tuple[str, float]] = []

    def lock_then_wait(conn, isbns):
        rows = real_lock(conn, isbns)
        events.append((threading.current_thread().name, time.monotonic()))
        time.sleep(0.4)
        return rows

    monkeypatch.setattr(order_repository, "lock_books", lock_then_wait)
    return events


def _run_parallel(app, calls):
    """calls: list of (name, method, url, json, headers). Returns {name: response}."""
    barrier = threading.Barrier(len(calls))
    results = {}

    def worker(name, method, url, body, headers):
        client = app.test_client()
        barrier.wait()
        results[name] = getattr(client, method)(url, json=body, headers=headers)

    threads = [threading.Thread(target=worker, name=c[0], args=c) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


# ---------------------------------------------------------------------------
# Creation, trigger, CHECKs, prices
# ---------------------------------------------------------------------------

def test_create_order_uses_defaults_trigger_and_generated_subtotal(it_client, h, seed, sql):
    response = it_client.post("/orders", json=order_body((B3, 2), (B1, 2), (B1, 1)), headers=h["u1"])

    assert response.status_code == 201
    data = response.get_json()["data"]
    pedido_id = data["pedido_id"]
    assert data["estado"] == "pending"
    assert data["usuario_id"] == seed["u1"]
    assert data["items"] == [
        {"isbn": B1, "titulo": "IT 1", "cantidad": 3, "precio_unitario": "10.50", "subtotal": "31.50"},
        {"isbn": B3, "titulo": "IT 3", "cantidad": 2, "precio_unitario": "7.25", "subtotal": "14.50"},
    ]
    total, estado = _one(sql, "SELECT total, estado FROM pedidos WHERE pedido_id = %s", (pedido_id,))
    assert total == Decimal("46.00") == _one(
        sql, "SELECT sum(subtotal) FROM pedido_detalle WHERE pedido_id = %s", (pedido_id,)
    )[0]
    assert data["total"] == "46.00"
    assert estado == "pending"
    assert _stock(sql, B1) == 2 and _stock(sql, B3) == 48


def test_exact_stock_leaves_zero(it_client, h, sql):
    assert it_client.post("/orders", json=order_body((B2, 1)), headers=h["u1"]).status_code == 201
    assert _stock(sql, B2) == 0


def test_rejections_leave_no_trace(it_client, h, seed, sql):
    stocks = {isbn: _stock(sql, isbn) for isbn in IT_BOOKS}

    short = it_client.post("/orders", json=order_body((B1, 1), (B2, 2)), headers=h["u1"])
    missing = it_client.post("/orders", json=order_body((B1, 1), (MISSING, 1)), headers=h["u1"])
    inactive = it_client.post("/orders", json=order_body((B1, 1)), headers=h["inactive"])

    assert (short.status_code, short.get_json()["code"]) == (409, "INSUFFICIENT_STOCK")
    assert (missing.status_code, missing.get_json()["code"]) == (404, "BOOK_NOT_FOUND")
    assert (inactive.status_code, inactive.get_json()["code"]) == (403, "USER_INACTIVE")
    assert {isbn: _stock(sql, isbn) for isbn in IT_BOOKS} == stocks
    assert _orders_of(sql, seed["u1"]) == 0 and _orders_of(sql, seed["inactive"]) == 0


def test_price_is_frozen_in_pedido_detalle(it_client, h, sql):
    pedido_id = it_client.post("/orders", json=order_body((B1, 1)), headers=h["u1"]).get_json()["data"]["pedido_id"]

    _one(sql, "UPDATE libros SET precio = 999.99 WHERE isbn = %s RETURNING isbn", (B1,))

    data = it_client.get(f"/orders/{pedido_id}/items", headers=h["u1"]).get_json()["data"]
    assert data["items"][0]["precio_unitario"] == "10.50"
    assert data["order"]["total"] == "10.50"


# ---------------------------------------------------------------------------
# Atomicity with real rollback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failing", ["insert_item", "change_stock"])
def test_failure_after_partial_writes_rolls_back_everything(it_client, h, seed, sql, monkeypatch, failing):
    from repositories import order_repository

    real = getattr(order_repository, failing)

    def fail_on_second(conn, *args):
        isbn = args[1] if failing == "insert_item" else args[0]
        if isbn == B3:
            raise RuntimeError("simulated failure after partial writes")
        return real(conn, *args)

    monkeypatch.setattr(order_repository, failing, fail_on_second)
    stocks = {isbn: _stock(sql, isbn) for isbn in IT_BOOKS}
    next_id_before = _one(sql, "SELECT last_value FROM pedidos_pedido_id_seq")[0]

    response = it_client.post("/orders", json=order_body((B1, 2), (B3, 1)), headers=h["u1"])

    assert response.status_code == 500
    assert _orders_of(sql, seed["u1"]) == 0
    assert _one(sql, "SELECT count(*) FROM pedido_detalle WHERE pedido_id > %s", (next_id_before,))[0] == 0
    assert {isbn: _stock(sql, isbn) for isbn in IT_BOOKS} == stocks


def test_stock_check_constraint_is_the_last_barrier(it_client, h, seed, sql, monkeypatch):
    """Pretend the locked read saw more stock: the real CHECK stops the UPDATE."""
    from repositories import order_repository

    real_lock = order_repository.lock_books

    def optimistic(conn, isbns):
        rows = real_lock(conn, isbns)
        return {isbn: {**row, "stock": 1000} for isbn, row in rows.items()}

    monkeypatch.setattr(order_repository, "lock_books", optimistic)

    response = it_client.post("/orders", json=order_body((B2, 2)), headers=h["u1"])

    assert response.status_code == 409
    assert response.get_json()["code"] == "INSUFFICIENT_STOCK"  # libros_stock_check
    assert _stock(sql, B2) == 1
    assert _orders_of(sql, seed["u1"]) == 0


# ---------------------------------------------------------------------------
# Concurrency (real threads, real connections, real row locks)
# ---------------------------------------------------------------------------

def test_two_buyers_of_the_last_copy_only_one_wins(it_app, h, seed, sql, slow_locks):
    results = _run_parallel(
        it_app,
        [
            ("buyer-1", "post", "/orders", order_body((B2, 1)), h["u1"]),
            ("buyer-2", "post", "/orders", order_body((B2, 1)), h["u2"]),
        ],
    )

    statuses = sorted(r.status_code for r in results.values())
    assert statuses == [201, 409]
    loser = next(r for r in results.values() if r.status_code == 409).get_json()
    assert loser["code"] == "INSUFFICIENT_STOCK"
    # The loser waited on the row lock and then READ the committed stock (0):
    # the rejection came from the locked read, not from the CHECK fallback.
    assert loser["details"]["items"] == [{"isbn": B2, "requested": 1, "available": 0}]
    assert _stock(sql, B2) == 0
    assert _one(sql, "SELECT coalesce(sum(cantidad), 0) FROM pedido_detalle WHERE isbn = %s", (B2,))[0] == 1
    assert _orders_of(sql, seed["u1"]) + _orders_of(sql, seed["u2"]) == 1
    # The second lock was granted only after the first transaction released it.
    (_, first), (_, second) = sorted(slow_locks, key=lambda e: e[1])
    assert second - first >= 0.35


def test_multi_book_orders_in_opposite_order_do_not_deadlock(it_app, h, seed, sql, slow_locks):
    calls = []
    for n in range(6):
        lines = ((B3, 1), (B4, 1)) if n % 2 == 0 else ((B4, 1), (B3, 1))
        calls.append((f"t{n}", "post", "/orders", order_body(*lines), h["u1"] if n % 2 else h["u2"]))

    results = _run_parallel(it_app, calls)

    assert [r.status_code for r in results.values()] == [201] * 6
    assert _stock(sql, B3) == 44 and _stock(sql, B4) == 44


def test_concurrent_cancellations_restore_stock_once(it_app, it_client, h, seed, sql, slow_locks):
    pedido_id = it_client.post("/orders", json=order_body((B1, 3)), headers=h["u1"]).get_json()["data"]["pedido_id"]
    assert _stock(sql, B1) == 2

    results = _run_parallel(
        it_app,
        [
            ("cancel-1", "patch", f"/orders/{pedido_id}/status", {"estado": "cancelled"}, h["admin"]),
            ("cancel-2", "patch", f"/orders/{pedido_id}/status", {"estado": "cancelled"}, h["admin"]),
        ],
    )

    codes = sorted((r.status_code, r.get_json().get("code")) for r in results.values())
    assert codes == [(200, None), (409, "ORDER_ALREADY_CANCELLED")]
    assert _stock(sql, B1) == 5


# ---------------------------------------------------------------------------
# Status, ownership, history
# ---------------------------------------------------------------------------

def test_status_flow_and_history(it_client, h, seed, sql):
    pedido_id = it_client.post("/orders", json=order_body((B1, 1), (B3, 2)), headers=h["u1"]).get_json()["data"]["pedido_id"]

    assert it_client.patch(f"/orders/{pedido_id}/status", json={"estado": "paid"}, headers=h["admin"]).status_code == 409
    assert it_client.patch(f"/orders/{pedido_id}/status", json={"estado": "cancelled"}, headers=h["admin"]).status_code == 200
    assert _stock(sql, B1) == 5 and _stock(sql, B3) == 50

    # History kept: the order and its lines (with prices and total) remain.
    assert _one(sql, "SELECT estado, total FROM pedidos WHERE pedido_id = %s", (pedido_id,)) == ("cancelled", Decimal("25.00"))
    assert _one(sql, "SELECT count(*) FROM pedido_detalle WHERE pedido_id = %s", (pedido_id,))[0] == 2

    other = it_client.post("/orders", json=order_body((B1, 1)), headers=h["u1"]).get_json()["data"]["pedido_id"]
    _one(sql, "UPDATE pedidos SET estado = 'paid' WHERE pedido_id = %s RETURNING pedido_id", (other,))
    response = it_client.patch(f"/orders/{other}/status", json={"estado": "completed"}, headers=h["admin"])
    assert response.status_code == 200
    assert response.get_json()["data"]["estado"] == "completed"
    assert _stock(sql, B1) == 4  # completing does not touch stock


def test_ownership_and_lists(it_client, h, seed):
    mine = it_client.post("/orders", json=order_body((B3, 1)), headers=h["u1"]).get_json()["data"]["pedido_id"]
    theirs = it_client.post("/orders", json=order_body((B4, 1)), headers=h["u2"]).get_json()["data"]["pedido_id"]

    assert it_client.get(f"/orders/{mine}", headers=h["u1"]).status_code == 200
    assert it_client.get(f"/orders/{theirs}", headers=h["u1"]).get_json()["code"] == "ORDER_NOT_FOUND"
    assert it_client.get(f"/orders/{theirs}/items", headers=h["u1"]).status_code == 404
    assert [o["pedido_id"] for o in it_client.get("/orders/me", headers=h["u1"]).get_json()["data"]] == [mine]

    listed = it_client.get(f"/orders?usuario_id={seed['u2']}", headers=h["admin"]).get_json()
    assert [o["pedido_id"] for o in listed["data"]] == [theirs]
    assert it_client.get("/orders?estado=pending&limit=1", headers=h["admin"]).get_json()["pagination"]["total"] >= 2
    assert it_client.delete(f"/orders/{mine}", headers=h["admin"]).status_code == 405
