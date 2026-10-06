from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg2 import errors as pg_errors

from catalog.errors import (
    book_already_exists,
    book_has_order_history,
    book_in_use,
    invalid_input,
    invalid_reference,
)
from catalog.validation import MUTABLE_FIELDS
from db.connection import transaction


# `conceptos` has no topic/category column (see db/01_schema.sql: only
# concepto_id + nombre), so there is no FK-based way to ask PostgreSQL
# "give me the Cloud Computing concepts". This is the real, confirmed set
# of Cloud Computing concept names present in the database (given by the
# course instructions); filtering by this list is the only way to exclude
# unrelated concepts without adding a schema column, which was not asked
# for. The comparison is case-insensitive because the exact casing stored
# in the database was not independently verified here (no reachable
# PostgreSQL instance in this environment, see 01_prompt_bilingue.md
# report, section K).
CLOUD_COMPUTING_CONCEPT_NAMES = (
    "IaaS",
    "PaaS",
    "SaaS",
    "FaaS",
    "Bucket",
    "Public Cloud",
    "Private Cloud",
    "Hybrid Cloud",
    "Multicloud",
    "Serverless",
)


_BOOK_SELECT = """
    SELECT
        l.isbn,
        l.titulo,
        l.anio_publicacion,
        l.precio,
        l.stock,
        c.nombre AS categoria,
        f.nombre AS formato
    FROM libros l
    JOIN categorias c ON c.categoria_id = l.categoria_id
    JOIN formatos f ON f.formato_id = l.formato_id
"""


def _escape_like(value: str) -> str:
    # Treat the search text literally: % and _ are not wildcards for the user.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_books(search: str | None = None) -> list[dict[str, Any]]:
    """
    Whole catalog, or filtered by a case-insensitive fragment of the title
    or ISBN (same semantics as fn_libros_listar / RF-06). Ordered by ISBN,
    as before.
    """
    pattern = f"%{_escape_like(search)}%" if search else None

    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _BOOK_SELECT
                + """
                WHERE %s::text IS NULL OR l.titulo ILIKE %s OR l.isbn ILIKE %s
                ORDER BY l.isbn;
                """,
                (pattern, pattern, pattern),
            )
            rows = cur.fetchall()

    return [_row_to_book(row) for row in rows]


def _select_book(cur, isbn: str) -> dict[str, Any] | None:
    cur.execute(_BOOK_SELECT + " WHERE l.isbn = %s;", (isbn,))
    row = cur.fetchone()
    return _row_to_book(row) if row is not None else None


def get_book(isbn: str) -> dict[str, Any] | None:
    with transaction() as conn:
        with conn.cursor() as cur:
            return _select_book(cur, isbn)


def _row_to_book(row) -> dict[str, Any]:
    return {
        "isbn": row[0],
        "titulo": row[1],
        "anio_publicacion": row[2],
        "precio": row[3],
        "stock": row[4],
        "categoria": row[5],
        "formato": row[6],
    }


# ---------------------------------------------------------------------------
# Writes (POST/PUT/PATCH/DELETE /books). Each runs in ONE transaction: any
# exception rolls back (db.connection.transaction) and nothing is committed.
# Values arrive already validated by catalog/validation.py; column names in
# dynamic SQL come only from the MUTABLE_FIELDS whitelist, never from input.
# ---------------------------------------------------------------------------

def _map_write_error(exc: Exception):
    if isinstance(exc, pg_errors.UniqueViolation):
        return book_already_exists()
    if isinstance(exc, pg_errors.ForeignKeyViolation):
        return invalid_reference()
    if isinstance(exc, (pg_errors.CheckViolation, pg_errors.NotNullViolation)):
        return invalid_input("The book data violates a database constraint.")
    return None


def _run_write(func):
    try:
        return func()
    except (pg_errors.IntegrityError, pg_errors.DataError) as exc:
        mapped = _map_write_error(exc)
        if mapped is None:
            raise
        raise mapped from exc


def create_book(isbn: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = ["isbn", *(f for f in MUTABLE_FIELDS if f in values)]
    params = [isbn, *(values[f] for f in columns[1:])]
    sql = f"INSERT INTO libros ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))});"

    def run():
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return _select_book(cur, isbn)

    return _run_write(run)


def update_book(isbn: str, values: dict[str, Any]) -> dict[str, Any] | None:
    """
    Updates ONLY the given columns (PATCH) or all of them (PUT). Returns
    None when the ISBN does not exist. fecha_actualizacion is maintained by
    trg_libros_set_fecha_actualizacion (05_triggers.sql).
    """
    columns = [f for f in MUTABLE_FIELDS if f in values]
    assignments = ", ".join(f"{column} = %s" for column in columns)
    sql = f"UPDATE libros SET {assignments} WHERE isbn = %s;"

    def run():
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [*(values[c] for c in columns), isbn])
                if cur.rowcount == 0:
                    return None
                return _select_book(cur, isbn)

    return _run_write(run)


ORDER_HISTORY_CONSTRAINT = "fk_pedido_detalle_libro"


def delete_book(isbn: str) -> bool:
    """
    Physical DELETE, the same operation the monolith performs
    (sp_libro_eliminar). Returns False when the ISBN does not exist.

    If the book was sold (pedido_detalle, ON DELETE RESTRICT, migration 07)
    PostgreSQL rejects the DELETE and the transaction is rolled back: no
    order line is touched, and the caller gets a 409 instead of a 500.
    """
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM libros WHERE isbn = %s;", (isbn,))
                return cur.rowcount > 0
    except pg_errors.ForeignKeyViolation as exc:
        constraint = getattr(exc.diag, "constraint_name", None)
        if constraint == ORDER_HISTORY_CONSTRAINT:
            raise book_has_order_history() from exc
        raise book_in_use() from exc


def to_cacheable(book: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe copy (Decimal -> str) that serializes exactly like the original."""
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in book.items()}


def list_cloud_concepts() -> list[dict[str, Any]]:
    """
    Returns every (concept, book) association restricted to the Cloud
    Computing concepts in CLOUD_COMPUTING_CONCEPT_NAMES (IaaS, PaaS, SaaS,
    FaaS, Bucket, Public/Private/Hybrid Cloud, Multicloud, Serverless).

    Does not invent or hardcode any concept *data* (id, definition, isbn,
    book title): all of that still comes from a real, parameterized query
    against conceptos/libro_concepto/libros. Only the set of concept
    *names* considered "Cloud Computing" is fixed, because the schema has
    no column to derive that distinction from.
    """
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.concepto_id,
                    c.nombre,
                    lc.definicion,
                    lc.isbn,
                    l.titulo
                FROM libro_concepto lc
                JOIN conceptos c ON c.concepto_id = lc.concepto_id
                JOIN libros l ON l.isbn = lc.isbn
                WHERE lower(c.nombre) = ANY(%s)
                ORDER BY c.concepto_id, lc.isbn;
                """,
                ([name.lower() for name in CLOUD_COMPUTING_CONCEPT_NAMES],),
            )
            rows = cur.fetchall()

    return [
        {
            "concepto_id": row[0],
            "concepto": row[1],
            "definicion": row[2],
            "isbn": row[3],
            "titulo_libro": row[4],
        }
        for row in rows
    ]


def list_books_with_images() -> list[dict[str, Any]]:
    """
    Datos minimos de cada libro (isbn, titulo, anio_publicacion, precio) mas
    sus autores reales (libro_autor + autores, respetando libro_autor.orden)
    y sus imagenes reales (imagenes_libro).

    Se ejecutan tres SELECT independientes (libros; libro_autor+autores;
    imagenes_libro) en vez de un unico JOIN de tres tablas porque un libro
    puede tener varios autores Y varias imagenes a la vez: un JOIN directo
    produciria el producto cartesiano autores x imagenes por libro (filas
    duplicadas que habria que des-duplicar despues). Construir cada lista
    (autores, images) desde su propia consulta y combinarlas en Python por
    isbn evita ese problema por diseno, sin necesitar DISTINCT ni agregacion
    SQL adicional.
    """
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT isbn, titulo, anio_publicacion, precio
                FROM libros
                ORDER BY isbn;
                """
            )
            book_rows = cur.fetchall()

            cur.execute(
                """
                SELECT la.isbn, a.nombre, a.apellido
                FROM libro_autor la
                JOIN autores a ON a.autor_id = la.autor_id
                ORDER BY la.isbn, la.orden, a.autor_id;
                """
            )
            author_rows = cur.fetchall()

            cur.execute(
                """
                SELECT isbn, url, texto_alternativo, orden, es_portada
                FROM imagenes_libro
                ORDER BY isbn, orden;
                """
            )
            image_rows = cur.fetchall()

    authors_by_isbn: dict[str, list[str]] = {}
    for isbn, nombre, apellido in author_rows:
        authors_by_isbn.setdefault(isbn, []).append(f"{nombre} {apellido}".strip())

    images_by_isbn: dict[str, list[dict[str, Any]]] = {}
    for isbn, url, texto_alternativo, orden, es_portada in image_rows:
        images_by_isbn.setdefault(isbn, []).append(
            {
                "url": url,
                "texto_alternativo": texto_alternativo,
                "orden": orden,
                "es_portada": es_portada,
            }
        )

    return [
        {
            "isbn": isbn,
            "titulo": titulo,
            "anio_publicacion": anio_publicacion,
            "precio": precio,
            "autores": authors_by_isbn.get(isbn, []),
            "images": images_by_isbn.get(isbn, []),
        }
        for isbn, titulo, anio_publicacion, precio in book_rows
    ]
