"""
SQL access to pedidos / pedido_detalle / libros / usuarios. Every query is
parametrized and NOTHING here commits: the service layer owns the
transaction (db.connection.transaction), so a whole order is written or
nothing is.

pedidos.total is never written here: trg_pedido_detalle_recalcular_total
(migration 07) recomputes it from pedido_detalle after every line change.
pedidos.estado is only written by set_status; its initial value is the
column DEFAULT ('pending').
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row


_ORDER_COLUMNS = """
    p.pedido_id, p.usuario_id, p.estado, p.total, p.fecha_creacion, p.fecha_actualizacion,
    (SELECT count(*) FROM pedido_detalle d WHERE d.pedido_id = p.pedido_id) AS items_count
"""


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    if filters.get("usuario_id") is not None:
        clauses.append("p.usuario_id = %s")
        params.append(filters["usuario_id"])
    if filters.get("estado"):
        clauses.append("p.estado = %s")
        params.append(filters["estado"])
    if filters.get("desde"):
        clauses.append("p.fecha_creacion >= %s")
        params.append(filters["desde"])
    if filters.get("hasta"):
        clauses.append("p.fecha_creacion < %s")
        params.append(filters["hasta"])
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_orders(conn: psycopg.Connection, filters: dict[str, Any], limit: int, offset: int) -> list[dict[str, Any]]:
    where, params = _where(filters)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_ORDER_COLUMNS}
            FROM pedidos p
            {where}
            ORDER BY p.fecha_creacion DESC, p.pedido_id DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        return cur.fetchall()


def count_orders(conn: psycopg.Connection, filters: dict[str, Any]) -> int:
    where, params = _where(filters)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM pedidos p {where}", params)
        return int(cur.fetchone()[0])


def get_order(conn: psycopg.Connection, pedido_id: int, for_update: bool = False) -> dict[str, Any] | None:
    """
    for_update=True locks the order row: two concurrent status changes of
    the same order run one after the other, so the second one sees the
    first one's result (e.g. a repeated cancellation never restores stock
    twice).
    """
    lock = "FOR UPDATE OF p" if for_update else ""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_ORDER_COLUMNS} FROM pedidos p WHERE p.pedido_id = %s {lock}", (pedido_id,))
        return cur.fetchone()


def list_items(conn: psycopg.Connection, pedido_id: int) -> list[dict[str, Any]]:
    """precio_unitario is the price frozen at purchase time, not libros.precio."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT d.isbn, l.titulo, d.cantidad, d.precio_unitario, d.subtotal
            FROM pedido_detalle d
            JOIN libros l ON l.isbn = d.isbn
            WHERE d.pedido_id = %s
            ORDER BY d.isbn
            """,
            (pedido_id,),
        )
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Writes (always inside the caller's transaction)
# ---------------------------------------------------------------------------

def get_user_activo(conn: psycopg.Connection, usuario_id: int) -> bool | None:
    """
    None if the user does not exist. FOR KEY SHARE keeps the row from being
    deleted until the order is committed (it does not block profile edits).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT activo FROM usuarios WHERE usuario_id = %s FOR KEY SHARE", (usuario_id,))
        row = cur.fetchone()
        return None if row is None else bool(row[0])


def lock_books(conn: psycopg.Connection, isbns: list[str]) -> dict[str, dict[str, Any]]:
    """
    SELECT ... ORDER BY isbn FOR UPDATE: the row locks are taken in ISBN
    order (the locking step runs on the sorted rows), the same order in
    every transaction, so two orders sharing books cannot deadlock each
    other. Locked rows cannot change stock/price until this transaction
    ends; a concurrent buyer of the same book waits here and then reads
    the already-decremented stock.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT isbn, titulo, precio, stock
            FROM libros
            WHERE isbn = ANY(%s)
            ORDER BY isbn
            FOR UPDATE
            """,
            (sorted(isbns),),
        )
        return {row["isbn"]: row for row in cur.fetchall()}


def insert_order(conn: psycopg.Connection, usuario_id: int) -> int:
    """estado, total and timestamps come from the column DEFAULTs."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO pedidos (usuario_id) VALUES (%s) RETURNING pedido_id", (usuario_id,))
        return int(cur.fetchone()[0])


def insert_item(conn: psycopg.Connection, pedido_id: int, isbn: str, cantidad: int, precio_unitario) -> None:
    """subtotal is GENERATED by PostgreSQL; the total trigger fires after this."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pedido_detalle (pedido_id, isbn, cantidad, precio_unitario) VALUES (%s, %s, %s, %s)",
            (pedido_id, isbn, cantidad, precio_unitario),
        )


def change_stock(conn: psycopg.Connection, isbn: str, delta: int) -> None:
    """
    Relative update (stock = stock + delta) on a row this transaction has
    already locked. libros_stock_check (stock >= 0) is the final barrier.
    """
    with conn.cursor() as cur:
        cur.execute("UPDATE libros SET stock = stock + %s WHERE isbn = %s", (delta, isbn))
        if cur.rowcount != 1:
            raise RuntimeError("Locked book row disappeared during the transaction.")


def set_status(conn: psycopg.Connection, pedido_id: int, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE pedidos SET estado = %s WHERE pedido_id = %s", (estado, pedido_id))


def get_order_items_for_restock(conn: psycopg.Connection, pedido_id: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT isbn, cantidad FROM pedido_detalle WHERE pedido_id = %s ORDER BY isbn",
            (pedido_id,),
        )
        return cur.fetchall()

