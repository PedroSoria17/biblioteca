"""
SQL access to autores / libro_autor / libros. Every query is parametrized.

This module never writes libros: it only reads it to validate that an ISBN
exists (PostgreSQL is the shared source of truth, no HTTP call to Books).
The only DELETE statements target autores (one row) and libro_autor (one
relation row).
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


_AUTHOR_COLUMNS = """
    a.autor_id, a.nombre, a.apellido, a.pais,
    (SELECT count(*) FROM libro_autor la WHERE la.autor_id = a.autor_id) AS books_count
"""

_UPDATABLE_COLUMNS = frozenset({"nombre", "apellido", "pais"})


def _like_pattern(q: str) -> str:
    # q is a literal substring: escape LIKE wildcards typed by the client.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search_clause(q: str | None) -> tuple[str, list[Any]]:
    """Search on the author's own text columns: nombre, apellido and pais."""
    if not q:
        return "", []
    pattern = _like_pattern(q)
    return (
        """
        WHERE a.nombre ILIKE %s
           OR a.apellido ILIKE %s
           OR (a.nombre || ' ' || a.apellido) ILIKE %s
           OR a.pais ILIKE %s
        """,
        [pattern, pattern, pattern, pattern],
    )


def list_authors(conn: psycopg.Connection, limit: int, offset: int, q: str | None) -> list[dict[str, Any]]:
    where, params = _search_clause(q)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_AUTHOR_COLUMNS}
            FROM autores a
            {where}
            ORDER BY a.apellido, a.nombre, a.autor_id
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        return cur.fetchall()


def count_authors(conn: psycopg.Connection, q: str | None) -> int:
    where, params = _search_clause(q)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM autores a {where}", params)
        return int(cur.fetchone()[0])


def get_author(conn: psycopg.Connection, autor_id: int, for_update: bool = False) -> dict[str, Any] | None:
    lock = "FOR UPDATE OF a" if for_update else ""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_AUTHOR_COLUMNS} FROM autores a WHERE a.autor_id = %s {lock}",
            (autor_id,),
        )
        return cur.fetchone()


def insert_author(conn: psycopg.Connection, nombre: str, apellido: str, pais: str | None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO autores (nombre, apellido, pais) VALUES (%s, %s, %s) RETURNING autor_id",
            (nombre, apellido, pais),
        )
        return int(cur.fetchone()[0])


def update_author(conn: psycopg.Connection, autor_id: int, changes: dict[str, Any]) -> None:
    if not changes:
        return
    invalid = set(changes) - _UPDATABLE_COLUMNS
    if invalid:
        raise ValueError(f"Columns not updatable: {sorted(invalid)}")

    columns = sorted(changes)
    assignments = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns)
    query = sql.SQL("UPDATE autores SET {} WHERE autor_id = %s").format(assignments)
    with conn.cursor() as cur:
        cur.execute(query, [changes[c] for c in columns] + [autor_id])


def delete_author(conn: psycopg.Connection, autor_id: int) -> None:
    """
    libro_autor.autor_id is ON DELETE RESTRICT: PostgreSQL refuses this if
    any relation still exists. Nothing cascades from autores, so a book can
    never be removed by this statement.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM autores WHERE autor_id = %s", (autor_id,))


def list_author_books(conn: psycopg.Connection, autor_id: int) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT l.isbn, l.titulo, l.anio_publicacion, la.orden
            FROM libro_autor la
            JOIN libros l ON l.isbn = la.isbn
            WHERE la.autor_id = %s
            ORDER BY l.titulo, l.isbn
            """,
            (autor_id,),
        )
        return cur.fetchall()


def get_book(conn: psycopg.Connection, isbn: str) -> dict[str, Any] | None:
    """Read-only existence check on libros (Books owns its writes)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT isbn, titulo, anio_publicacion FROM libros WHERE isbn = %s", (isbn,))
        return cur.fetchone()


def relation_exists(conn: psycopg.Connection, autor_id: int, isbn: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM libro_autor WHERE autor_id = %s AND isbn = %s)", (autor_id, isbn))
        return bool(cur.fetchone()[0])


def next_orden(conn: psycopg.Connection, isbn: str) -> int:
    """Position after the book's current authors (1 for a book without authors)."""
    with conn.cursor() as cur:
        # LEAST: never overflow SMALLINT (orden is only a display position).
        cur.execute("SELECT LEAST(COALESCE(MAX(orden), 0) + 1, 32767) FROM libro_autor WHERE isbn = %s", (isbn,))
        return int(cur.fetchone()[0])


def insert_relation(conn: psycopg.Connection, autor_id: int, isbn: str, orden: int) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO libro_autor (isbn, autor_id, orden) VALUES (%s, %s, %s)", (isbn, autor_id, orden))


def delete_relation(conn: psycopg.Connection, autor_id: int, isbn: str) -> bool:
    """Removes ONE libro_autor row. Neither the author nor the book is touched."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM libro_autor WHERE autor_id = %s AND isbn = %s", (autor_id, isbn))
        return cur.rowcount > 0
