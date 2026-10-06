"""
SQL access to usuarios / roles / pedidos. Every query is parametrized.

Reads NEVER select password_hash: the only statements that touch it are the
INSERT and the UPDATE, which receive an already computed bcrypt hash.

es_administrador is never written here. Only role_id is written and
trg_usuarios_sincronizar_rol (data/07_microservices_auth_orders_payments.sql)
keeps es_administrador in sync, so ck_usuarios_role_admin_sync and
ux_usuarios_un_solo_administrador keep working as the final barrier.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from library_shared.roles import ROLE_ADMIN


_PUBLIC_COLUMNS = """
    u.usuario_id, u.nombre_completo, u.email, u.role_id, r.codigo AS role,
    u.activo, u.fecha_registro
"""

# Column names that update_user may write. Guards the dynamic SET clause:
# anything else is a programming error, never user input.
_UPDATABLE_COLUMNS = frozenset({"nombre_completo", "email", "password_hash", "role_id", "activo"})


def list_users(conn: psycopg.Connection, limit: int, offset: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PUBLIC_COLUMNS}
            FROM usuarios u
            LEFT JOIN roles r ON r.role_id = u.role_id
            ORDER BY u.usuario_id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return cur.fetchall()


def count_users(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM usuarios")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def get_user(conn: psycopg.Connection, usuario_id: int, for_update: bool = False) -> dict[str, Any] | None:
    """
    for_update=True locks the row until the transaction ends, so two
    concurrent admin operations on the same user (e.g. demote + delete) are
    validated one after the other.
    """
    lock = "FOR UPDATE OF u" if for_update else ""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PUBLIC_COLUMNS}
            FROM usuarios u
            LEFT JOIN roles r ON r.role_id = u.role_id
            WHERE u.usuario_id = %s
            {lock}
            """,
            (usuario_id,),
        )
        return cur.fetchone()


def email_taken(conn: psycopg.Connection, email: str, exclude_usuario_id: int | None = None) -> bool:
    """
    Case-insensitive on purpose: the UNIQUE constraint is case-sensitive,
    and legacy rows may contain uppercase letters. Two accounts that only
    differ in case would be ambiguous for Login (which lowercases input).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM usuarios
                WHERE lower(email) = lower(%s)
                  AND (%s::bigint IS NULL OR usuario_id <> %s::bigint)
            )
            """,
            (email, exclude_usuario_id, exclude_usuario_id),
        )
        return bool(cur.fetchone()[0])


def role_exists(conn: psycopg.Connection, role_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM roles WHERE role_id = %s)", (role_id,))
        return bool(cur.fetchone()[0])


def admin_exists(conn: psycopg.Connection, exclude_usuario_id: int | None = None) -> bool:
    """Any ADMIN row, active or not (the unique index covers both)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM usuarios
                WHERE role_id = %s
                  AND (%s::bigint IS NULL OR usuario_id <> %s::bigint)
            )
            """,
            (ROLE_ADMIN, exclude_usuario_id, exclude_usuario_id),
        )
        return bool(cur.fetchone()[0])


def count_other_active_admins(conn: psycopg.Connection, usuario_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM usuarios WHERE role_id = %s AND activo AND usuario_id <> %s",
            (ROLE_ADMIN, usuario_id),
        )
        return int(cur.fetchone()[0])


def insert_user(
    conn: psycopg.Connection,
    nombre_completo: str,
    email: str,
    password_hash: str,
    role_id: int,
    activo: bool,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nombre_completo, email, password_hash, role_id, activo)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING usuario_id
            """,
            (nombre_completo, email, password_hash, role_id, activo),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def update_user(conn: psycopg.Connection, usuario_id: int, changes: dict[str, Any]) -> None:
    if not changes:
        return
    invalid = set(changes) - _UPDATABLE_COLUMNS
    if invalid:
        raise ValueError(f"Columns not updatable: {sorted(invalid)}")

    columns = sorted(changes)
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in columns
    )
    query = sql.SQL("UPDATE usuarios SET {} WHERE usuario_id = %s").format(assignments)

    with conn.cursor() as cur:
        cur.execute(query, [changes[column] for column in columns] + [usuario_id])


def has_orders(conn: psycopg.Connection, usuario_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM pedidos WHERE usuario_id = %s)", (usuario_id,))
        return bool(cur.fetchone()[0])


def delete_user(conn: psycopg.Connection, usuario_id: int) -> None:
    """
    usuario_detalle and usuario_verificacion_email go away by their own
    ON DELETE CASCADE (login_microservice.sql). pedidos is ON DELETE
    RESTRICT (migration 07): PostgreSQL rejects the delete if any exists.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM usuarios WHERE usuario_id = %s", (usuario_id,))
