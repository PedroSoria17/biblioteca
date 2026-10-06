"""
Integration tests against a REAL, DISPOSABLE PostgreSQL database.

Skipped unless PAYMENTS_IT_DB_NAME is set. The name MUST end in "_test"
(enforced below). They create and remove only their own rows (users
'it.payments.*', books in IT_BOOKS, and their orders/payments).

Verified for real: pagos constraints (uq_pagos_referencia,
ux_pagos_un_aprobado_por_pedido, ck_pagos_fecha_pago), row locks on pedidos
shared with Orders' cancellation, concurrent approvals and refunds, stock
restored exactly once, rollback of partial work.

Orders' cancellation is reproduced here with plain SQL following exactly
its strategy (lock pedidos FOR UPDATE, check 'pending', lock libros by
ISBN, restore stock, set 'cancelled'); importing Orders is not possible
because both services have top-level `services`/`repositories` packages.

Redis is NOT real here (in-memory fake from conftest.py).
"""

from __future__ import annotations

from decimal import Decimal
import os
import threading
import time

import psycopg
import pytest

from conftest import FakeRedis, bearer


IT_DB_NAME = os.getenv("PAYMENTS_IT_DB_NAME", "")

pytestmark = pytest.mark.skipif(not IT_DB_NAME, reason="PAYMENTS_IT_DB_NAME not set (no disposable PostgreSQL)")

IT_BOOKS = {"9793333333331": ("10.50", 10), "9793333333332": ("20.00", 10)}
B1, B2 = sorted(IT_BOOKS)


def _db_env() -> dict[str, str]:
    if not IT_DB_NAME.endswith("_test"):
        pytest.fail("PAYMENTS_IT_DB_NAME must end with '_test': these tests write and delete rows.")
    return {
        "DB_HOST": os.getenv("PAYMENTS_IT_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("PAYMENTS_IT_DB_PORT", "5432"),
        "DB_NAME": IT_DB_NAME,
        "DB_USER": os.getenv("PAYMENTS_IT_DB_USER", "library_user"),
        "DB_PASSWORD": os.getenv("PAYMENTS_IT_DB_PASSWORD", ""),
    }


def _connect(db_env, autocommit=True):
    return psycopg.connect(
        host=db_env["DB_HOST"], port=db_env["DB_PORT"], dbname=db_env["DB_NAME"],
        user=db_env["DB_USER"], password=db_env["DB_PASSWORD"], autocommit=autocommit,
    )


@pytest.fixture
def db_env(env, monkeypatch):
    values = _db_env()
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def sql(db_env):
    conn = _connect(db_env)
    try:
        yield conn
    finally:
        conn.close()


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


IT_ORDERS = "SELECT pedido_id FROM pedidos WHERE usuario_id IN (SELECT usuario_id FROM usuarios WHERE email LIKE 'it.payments.%%')"


def _cleanup(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM pagos WHERE pedido_id IN ({IT_ORDERS})")
        cur.execute(f"DELETE FROM pedido_detalle WHERE pedido_id IN ({IT_ORDERS})")
        cur.execute(f"DELETE FROM pedidos WHERE pedido_id IN ({IT_ORDERS})")
        cur.execute("DELETE FROM libros WHERE isbn = ANY(%s)", (list(IT_BOOKS),))
        cur.execute("DELETE FROM usuarios WHERE email LIKE 'it.payments.%%'")


@pytest.fixture
def seed(sql):
    _cleanup(sql)
    formato_id = _one(sql, "SELECT min(formato_id) FROM formatos")[0]
    categoria_id = _one(sql, "SELECT min(categoria_id) FROM categorias")[0]
    for isbn, (precio, stock) in IT_BOOKS.items():
        _one(
            sql,
            "INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id) "
            "VALUES (%s, 'IT', 2000, %s, %s, %s, %s) RETURNING isbn",
            (isbn, precio, stock, formato_id, categoria_id),
        )
    ids = {
        name: _one(
            sql,
            "INSERT INTO usuarios (nombre_completo, email, password_hash) VALUES ('IT', %s, 'x') RETURNING usuario_id",
            (f"it.payments.{name}@example.com",),
        )[0]
        for name in ("u1", "u2")
    }
    yield ids
    _cleanup(sql)


def make_order(db_env, usuario_id, lines) -> int:
    """What Orders' POST /orders commits: order + lines (frozen price) + stock taken."""
    with _connect(db_env, autocommit=False) as conn:
        pedido_id = _one(conn, "INSERT INTO pedidos (usuario_id) VALUES (%s) RETURNING pedido_id", (usuario_id,))[0]
        for isbn, cantidad in sorted(lines.items()):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pedido_detalle (pedido_id, isbn, cantidad, precio_unitario) "
                    "SELECT %s, isbn, %s, precio FROM libros WHERE isbn = %s",
                    (pedido_id, cantidad, isbn),
                )
                cur.execute("UPDATE libros SET stock = stock - %s WHERE isbn = %s", (cantidad, isbn))
        conn.commit()
    return pedido_id


def orders_cancel(db_env, pedido_id, hold_seconds=0.0) -> bool:
    """Orders' pending -> cancelled transaction (same locks, same order). True if it cancelled."""
    with _connect(db_env, autocommit=False) as conn:
        estado = _one(conn, "SELECT estado FROM pedidos WHERE pedido_id = %s FOR UPDATE", (pedido_id,))[0]
        time.sleep(hold_seconds)
        if estado != "pending":
            conn.rollback()
            return False
        with conn.cursor() as cur:
            cur.execute("SELECT isbn, cantidad FROM pedido_detalle WHERE pedido_id = %s ORDER BY isbn", (pedido_id,))
            items = cur.fetchall()
            cur.execute("SELECT isbn FROM libros WHERE isbn = ANY(%s) ORDER BY isbn FOR UPDATE", ([i[0] for i in items],))
            for isbn, cantidad in items:
                cur.execute("UPDATE libros SET stock = stock + %s WHERE isbn = %s", (cantidad, isbn))
            cur.execute("UPDATE pedidos SET estado = 'cancelled' WHERE pedido_id = %s", (pedido_id,))
        conn.commit()
        return True


@pytest.fixture
def it_redis():
    return FakeRedis()


@pytest.fixture
def it_app(db_env, seed, it_redis):
    from app import create_app
    from library_shared.redis_client import RedisGateway

    application = create_app(redis_gateway=RedisGateway(it_redis))
    application.testing = True
    return application


@pytest.fixture
def it_client(it_app):
    return it_app.test_client()


@pytest.fixture
def h(make_token, seed):
    headers = {name: bearer(make_token(uid, 1)) for name, uid in seed.items()}
    headers["admin"] = bearer(make_token(seed["u2"], 2))
    return headers


@pytest.fixture
def slow_order_lock(monkeypatch):
    """Hold the pedidos lock for a while so concurrent requests really overlap."""
    from repositories import payment_repository

    real = payment_repository.lock_order
    events = []

    def lock_then_wait(conn, pedido_id):
        row = real(conn, pedido_id)
        events.append((threading.current_thread().name, time.monotonic()))
        time.sleep(0.4)
        return row

    monkeypatch.setattr(payment_repository, "lock_order", lock_then_wait)
    return events


def _parallel(app, calls):
    barrier = threading.Barrier(len(calls))
    results = {}

    def worker(name, fn):
        barrier.wait()
        results[name] = fn()

    threads = [threading.Thread(target=worker, name=name, args=(name, fn)) for name, fn in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _stock(sql, isbn):
    return _one(sql, "SELECT stock FROM libros WHERE isbn = %s", (isbn,))[0]


def _payment_states(sql, pedido_id):
    with sql.cursor() as cur:
        cur.execute("SELECT estado FROM pagos WHERE pedido_id = %s ORDER BY pago_id", (pedido_id,))
        return [r[0] for r in cur.fetchall()]


def _register(client, headers, pedido_id, **extra):
    response = client.post("/payments", json={"pedido_id": pedido_id, "metodo_pago": "credit_card", **extra}, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["pago_id"]


# ---------------------------------------------------------------------------
# Happy paths and constraints
# ---------------------------------------------------------------------------

def test_register_and_approve(it_client, h, seed, db_env, sql):
    pedido = make_order(db_env, seed["u1"], {B1: 2, B2: 1})

    created = it_client.post("/payments", json={"pedido_id": pedido, "metodo_pago": "cash"}, headers=h["u1"])
    assert created.status_code == 201
    pago = created.get_json()["data"]
    assert pago["monto"] == "41.00" and pago["estado"] == "pending" and pago["fecha_pago"] is None

    approved = it_client.post(f"/payments/{pago['pago_id']}/approve", headers=h["admin"])
    assert approved.status_code == 200
    estado, monto, fecha_pago = _one(sql, "SELECT estado, monto, fecha_pago FROM pagos WHERE pago_id = %s", (pago["pago_id"],))
    assert (estado, monto) == ("approved", Decimal("41.00")) and fecha_pago is not None
    assert _one(sql, "SELECT estado, total FROM pedidos WHERE pedido_id = %s", (pedido,)) == ("paid", Decimal("41.00"))
    assert _stock(sql, B1) == 8 and _stock(sql, B2) == 9  # approval does not move stock


def test_reject_then_retry(it_client, h, seed, db_env, sql):
    pedido = make_order(db_env, seed["u1"], {B1: 1})
    first = _register(it_client, h["u1"], pedido)

    assert it_client.post(f"/payments/{first}/reject", headers=h["admin"]).status_code == 200
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "pending"

    second = _register(it_client, h["u1"], pedido)
    assert it_client.post(f"/payments/{second}/approve", headers=h["admin"]).status_code == 200
    assert _payment_states(sql, pedido) == ["rejected", "approved"]


def test_duplicate_referencia_hits_the_real_unique_constraint(it_client, h, seed, db_env, sql):
    pedido = make_order(db_env, seed["u1"], {B1: 1})
    _register(it_client, h["u1"], pedido, referencia="IT-REF-1")

    response = it_client.post(
        "/payments", json={"pedido_id": pedido, "metodo_pago": "cash", "referencia": "IT-REF-1"}, headers=h["u1"]
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_REFERENCE_EXISTS"  # uq_pagos_referencia
    assert _payment_states(sql, pedido) == ["pending"]


def test_one_approved_index_is_the_last_barrier(it_client, h, seed, db_env, sql, monkeypatch):
    """Skip the explicit check on a crafted state: the real partial unique index rejects it."""
    from repositories import payment_repository

    pedido = make_order(db_env, seed["u1"], {B1: 1})
    pending = _register(it_client, h["u1"], pedido)
    _one(
        sql,
        "INSERT INTO pagos (pedido_id, monto, metodo_pago, estado, referencia, fecha_pago) "
        "SELECT pedido_id, total, 'cash', 'approved', 'IT-CRAFTED', now() FROM pedidos WHERE pedido_id = %s RETURNING pago_id",
        (pedido,),
    )
    monkeypatch.setattr(payment_repository, "approved_payment_exists", lambda *_a, **_k: False)

    response = it_client.post(f"/payments/{pending}/approve", headers=h["admin"])

    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_ALREADY_APPROVED"  # ux_pagos_un_aprobado_por_pedido
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "pending"  # rolled back


def test_amount_is_frozen_and_checked(it_client, h, seed, db_env, sql):
    pedido = make_order(db_env, seed["u1"], {B1: 1})
    pago = _register(it_client, h["u1"], pedido)

    _one(sql, "UPDATE libros SET precio = 999 WHERE isbn = %s RETURNING isbn", (B1,))
    assert it_client.get(f"/payments/{pago}", headers=h["u1"]).get_json()["data"]["monto"] == "10.50"

    _one(sql, "UPDATE pedidos SET total = 11.00 WHERE pedido_id = %s RETURNING pedido_id", (pedido,))
    response = it_client.post(f"/payments/{pago}/approve", headers=h["admin"])
    assert response.get_json()["code"] == "PAYMENT_AMOUNT_MISMATCH"
    assert _payment_states(sql, pedido) == ["pending"]


@pytest.mark.parametrize("failing", ["set_order_status", "set_payment_status"])
def test_approval_rolls_back_on_failure(it_client, h, seed, db_env, sql, monkeypatch, failing):
    from repositories import payment_repository

    pedido = make_order(db_env, seed["u1"], {B1: 1})
    pago = _register(it_client, h["u1"], pedido)

    def broken(*_a, **_k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(payment_repository, failing, broken)

    assert it_client.post(f"/payments/{pago}/approve", headers=h["admin"]).status_code == 500
    assert _payment_states(sql, pedido) == ["pending"]
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "pending"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------

def test_two_attempts_approved_concurrently_only_one_wins(it_app, it_client, h, seed, db_env, sql, slow_order_lock):
    pedido = make_order(db_env, seed["u1"], {B1: 1})
    first, second = _register(it_client, h["u1"], pedido), _register(it_client, h["u1"], pedido)
    slow_order_lock.clear()

    results = _parallel(it_app, [
        (name, lambda pago=pago: it_app.test_client().post(f"/payments/{pago}/approve", headers=h["admin"]))
        for name, pago in (("a", first), ("b", second))
    ])

    codes = sorted((r.status_code, r.get_json().get("code")) for r in results.values())
    assert codes == [(200, None), (409, "ORDER_NOT_PAYABLE")]
    assert sorted(_payment_states(sql, pedido)) == ["approved", "pending"]
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "paid"
    (_, t1), (_, t2) = sorted(slow_order_lock, key=lambda e: e[1])
    assert t2 - t1 >= 0.35  # the second waited for the first one's lock


def test_same_payment_approved_twice_concurrently(it_app, it_client, h, seed, db_env, sql, slow_order_lock):
    pedido = make_order(db_env, seed["u1"], {B1: 1})
    pago = _register(it_client, h["u1"], pedido)

    results = _parallel(it_app, [
        (name, lambda: it_app.test_client().post(f"/payments/{pago}/approve", headers=h["admin"]))
        for name in ("a", "b")
    ])

    codes = sorted((r.status_code, r.get_json().get("code")) for r in results.values())
    assert codes == [(200, None), (409, "PAYMENT_ALREADY_APPROVED")]
    assert _payment_states(sql, pedido) == ["approved"]


def test_approval_wins_against_cancellation(it_app, it_client, h, seed, db_env, sql, slow_order_lock):
    pedido = make_order(db_env, seed["u1"], {B1: 2})
    pago = _register(it_client, h["u1"], pedido)
    stock_reserved = _stock(sql, B1)

    def approve():
        return it_app.test_client().post(f"/payments/{pago}/approve", headers=h["admin"])

    def cancel_later():
        time.sleep(0.15)  # Payments takes the pedidos lock first
        return orders_cancel(db_env, pedido)

    results = _parallel(it_app, [("pay", approve), ("cancel", cancel_later)])

    assert results["pay"].status_code == 200
    assert results["cancel"] is False  # Orders saw 'paid' after waiting for the lock
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "paid"
    assert _payment_states(sql, pedido) == ["approved"]
    assert _stock(sql, B1) == stock_reserved  # stock NOT restored for a paid order


def test_cancellation_wins_against_approval(it_app, it_client, h, seed, db_env, sql):
    pedido = make_order(db_env, seed["u1"], {B1: 2})
    pago = _register(it_client, h["u1"], pedido)
    stock_reserved = _stock(sql, B1)

    def cancel_first():
        return orders_cancel(db_env, pedido, hold_seconds=0.4)

    def approve_later():
        time.sleep(0.15)  # Orders takes the pedidos lock first
        return it_app.test_client().post(f"/payments/{pago}/approve", headers=h["admin"])

    results = _parallel(it_app, [("cancel", cancel_first), ("pay", approve_later)])

    assert results["cancel"] is True
    assert results["pay"].status_code == 409
    assert results["pay"].get_json() == {
        "success": False,
        "code": "ORDER_NOT_PAYABLE",
        "message": "The order is 'cancelled' and can no longer be paid.",
        "details": {"order_estado": "cancelled"},
    }
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "cancelled"
    assert _payment_states(sql, pedido) == ["pending"]  # never approved
    assert _stock(sql, B1) == stock_reserved + 2  # restored once, by Orders


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------

def _paid(it_client, h, seed, db_env, lines):
    pedido = make_order(db_env, seed["u1"], lines)
    pago = _register(it_client, h["u1"], pedido)
    assert it_client.post(f"/payments/{pago}/approve", headers=h["admin"]).status_code == 200
    return pedido, pago


def test_refund_restores_stock_once_and_cancels(it_client, it_redis, h, seed, db_env, sql):
    pedido, pago = _paid(it_client, h, seed, db_env, {B2: 1, B1: 3})
    assert (_stock(sql, B1), _stock(sql, B2)) == (7, 9)
    it_redis.store.update({f"books:{B1}": "{}", "books:list:all": "[]"})

    response = it_client.post(f"/payments/{pago}/refund", headers=h["admin"])

    assert response.status_code == 200
    assert (_stock(sql, B1), _stock(sql, B2)) == (10, 10)
    estado, fecha_pago = _one(sql, "SELECT estado, fecha_pago FROM pagos WHERE pago_id = %s", (pago,))
    assert estado == "refunded" and fecha_pago is not None  # ck_pagos_fecha_pago
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "cancelled"
    assert it_redis.store == {}
    # History kept: lines and payment are still there.
    assert _one(sql, "SELECT count(*) FROM pedido_detalle WHERE pedido_id = %s", (pedido,))[0] == 2

    again = it_client.post(f"/payments/{pago}/refund", headers=h["admin"])
    assert again.get_json()["code"] == "PAYMENT_ALREADY_REFUNDED"
    assert (_stock(sql, B1), _stock(sql, B2)) == (10, 10)


def test_concurrent_refunds_restore_stock_once(it_app, it_client, h, seed, db_env, sql, slow_order_lock):
    _pedido, pago = _paid(it_client, h, seed, db_env, {B1: 4})
    assert _stock(sql, B1) == 6

    results = _parallel(it_app, [
        (name, lambda: it_app.test_client().post(f"/payments/{pago}/refund", headers=h["admin"]))
        for name in ("a", "b")
    ])

    codes = sorted((r.status_code, r.get_json().get("code")) for r in results.values())
    assert codes == [(200, None), (409, "PAYMENT_ALREADY_REFUNDED")]
    assert _stock(sql, B1) == 10


def test_refund_rolls_back_completely_on_failure(it_client, h, seed, db_env, sql, monkeypatch):
    from repositories import payment_repository

    pedido, pago = _paid(it_client, h, seed, db_env, {B1: 2})

    def broken(*_a, **_k):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(payment_repository, "set_order_status", broken)

    assert it_client.post(f"/payments/{pago}/refund", headers=h["admin"]).status_code == 500
    assert _stock(sql, B1) == 8
    assert _payment_states(sql, pedido) == ["approved"]
    assert _one(sql, "SELECT estado FROM pedidos WHERE pedido_id = %s", (pedido,))[0] == "paid"


def test_completed_order_is_not_refundable(it_client, h, seed, db_env, sql):
    pedido, pago = _paid(it_client, h, seed, db_env, {B1: 1})
    _one(sql, "UPDATE pedidos SET estado = 'completed' WHERE pedido_id = %s RETURNING pedido_id", (pedido,))

    response = it_client.post(f"/payments/{pago}/refund", headers=h["admin"])

    assert response.get_json()["code"] == "REFUND_NOT_ALLOWED"
    assert _stock(sql, B1) == 9


# ---------------------------------------------------------------------------
# Ownership and history
# ---------------------------------------------------------------------------

def test_ownership_and_no_deletes(it_client, h, seed, db_env, sql):
    mine = make_order(db_env, seed["u1"], {B1: 1})
    theirs = make_order(db_env, seed["u2"], {B2: 1})
    my_pago = _register(it_client, h["u1"], mine)
    their_pago = _register(it_client, h["u2"], theirs)

    assert it_client.post("/payments", json={"pedido_id": theirs, "metodo_pago": "cash"}, headers=h["u1"]).status_code == 404
    assert it_client.get(f"/payments/{their_pago}", headers=h["u1"]).status_code == 404
    assert it_client.get(f"/orders/{theirs}/payments", headers=h["u1"]).status_code == 404
    assert [p["pago_id"] for p in it_client.get("/payments/me", headers=h["u1"]).get_json()["data"]] == [my_pago]
    assert it_client.get(f"/payments?pedido_id={theirs}", headers=h["admin"]).get_json()["pagination"]["total"] == 1

    assert it_client.delete(f"/payments/{my_pago}", headers=h["admin"]).status_code == 405
    assert _one(sql, "SELECT count(*) FROM pagos WHERE pago_id = %s", (my_pago,))[0] == 1
