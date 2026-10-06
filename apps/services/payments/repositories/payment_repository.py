"""
SQL access to pagos / pedidos / pedido_detalle / libros / usuarios. Every
query is parametrized and NOTHING here commits: the service layer owns the
transaction.

Lock order, the same in every Payments transaction (and compatible with
Orders, which locks pedidos first and then libros by ISBN):

    1. pedidos row        lock_order()      SELECT ... FOR UPDATE
    2. pagos row          lock_payment()    SELECT ... FOR UPDATE
    3. libros rows        lock_books()      SELECT ... ORDER BY isbn FOR UPDATE  (refund only)

Payments never DELETEs anything and never writes pedido_detalle.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row


_PAYMENT_COLUMNS = """
    pg.pago_id, pg.pedido_id, p.usuario_id, pg.monto, pg.metodo_pago, pg.estado,
    pg.referencia, pg.fecha_pago, pg.fecha_creacion, pg.fecha_actualizacion
"""


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    for column, key in (("p.usuario_id", "usuario_id"), ("pg.pedido_id", "pedido_id"),
                        ("pg.estado", "estado"), ("pg.metodo_pago", "metodo_pago")):
        if filters.get(key) is not None:
            clauses.append(f"{column} = %s")
            params.append(filters[key])
    if filters.get("desde"):
        clauses.append("pg.fecha_creacion >= %s")
        params.append(filters["desde"])
    if filters.get("hasta"):
        clauses.append("pg.fecha_creacion < %s")
        params.append(filters["hasta"])
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_payments(conn: psycopg.Connection, filters: dict[str, Any], limit: int, offset: int) -> list[dict[str, Any]]:
    where, params = _where(filters)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PAYMENT_COLUMNS}
            FROM pagos pg JOIN pedidos p ON p.pedido_id = pg.pedido_id
            {where}
            ORDER BY pg.fecha_creacion DESC, pg.pago_id DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        return cur.fetchall()


def count_payments(conn: psycopg.Connection, filters: dict[str, Any]) -> int:
    where, params = _where(filters)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM pagos pg JOIN pedidos p ON p.pedido_id = pg.pedido_id {where}", params)
        return int(cur.fetchone()[0])


def get_payment(conn: psycopg.Connection, pago_id: int) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PAYMENT_COLUMNS} FROM pagos pg JOIN pedidos p ON p.pedido_id = pg.pedido_id WHERE pg.pago_id = %s",
            (pago_id,),
        )
        return cur.fetchone()


def get_order(conn: psycopg.Connection, pedido_id: int) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT pedido_id, usuario_id, estado, total FROM pedidos WHERE pedido_id = %s", (pedido_id,))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Locks and writes (always inside the caller's transaction)
# ---------------------------------------------------------------------------

def get_user_activo(conn: psycopg.Connection, usuario_id: int) -> bool | None:
    with conn.cursor() as cur:
        cur.execute("SELECT activo FROM usuarios WHERE usuario_id = %s", (usuario_id,))
        row = cur.fetchone()
        return None if row is None else bool(row[0])


def lock_order(conn: psycopg.Connection, pedido_id: int) -> dict[str, Any] | None:
    """
    The SAME row lock Orders takes to cancel: approval, refund and
    cancellation of one order are serialized, and each one re-reads the
    estado left by the previous one.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT pedido_id, usuario_id, estado, total FROM pedidos WHERE pedido_id = %s FOR UPDATE",
            (pedido_id,),
        )
        return cur.fetchone()


def lock_payment(conn: psycopg.Connection, pago_id: int) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT pago_id, pedido_id, monto, metodo_pago, estado, referencia FROM pagos WHERE pago_id = %s FOR UPDATE",
            (pago_id,),
        )
        return cur.fetchone()


def approved_payment_exists(conn: psycopg.Connection, pedido_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM pagos WHERE pedido_id = %s AND estado = 'approved')", (pedido_id,))
        return bool(cur.fetchone()[0])


def insert_payment(conn: psycopg.Connection, pedido_id: int, monto, metodo_pago: str, referencia: str) -> int:
    """estado ('pending'), fecha_pago (NULL) and timestamps come from the DEFAULTs."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pagos (pedido_id, monto, metodo_pago, referencia) VALUES (%s, %s, %s, %s) RETURNING pago_id",
            (pedido_id, monto, metodo_pago, referencia),
        )
        return int(cur.fetchone()[0])


def set_payment_status(conn: psycopg.Connection, pago_id: int, estado: str, set_fecha_pago: bool = False) -> None:
    """
    set_fecha_pago=True stamps fecha_pago = now() (approval). A refund keeps
    the original fecha_pago, which ck_pagos_fecha_pago also requires.
    """
    with conn.cursor() as cur:
        if set_fecha_pago:
            cur.execute("UPDATE pagos SET estado = %s, fecha_pago = now() WHERE pago_id = %s", (estado, pago_id))
        else:
            cur.execute("UPDATE pagos SET estado = %s WHERE pago_id = %s", (estado, pago_id))
        if cur.rowcount != 1:
            raise RuntimeError("Locked payment row disappeared during the transaction.")


def set_order_status(conn: psycopg.Connection, pedido_id: int, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE pedidos SET estado = %s WHERE pedido_id = %s", (estado, pedido_id))
        if cur.rowcount != 1:
            raise RuntimeError("Locked order row disappeared during the transaction.")


def get_order_items(conn: psycopg.Connection, pedido_id: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT isbn, cantidad FROM pedido_detalle WHERE pedido_id = %s ORDER BY isbn", (pedido_id,))
        return cur.fetchall()


def lock_books(conn: psycopg.Connection, isbns: list[str]) -> None:
    """Same deterministic order as Orders: by ISBN."""
    with conn.cursor() as cur:
        cur.execute("SELECT isbn FROM libros WHERE isbn = ANY(%s) ORDER BY isbn FOR UPDATE", (sorted(isbns),))
        cur.fetchall()


def add_stock(conn: psycopg.Connection, isbn: str, cantidad: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE libros SET stock = stock + %s WHERE isbn = %s", (cantidad, isbn))
        if cur.rowcount != 1:
            raise RuntimeError("Locked book row disappeared during the transaction.")
