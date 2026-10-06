"""
Business rules of the authors microservice.

Writes run in ONE PostgreSQL transaction. Explicit checks give clear
404/409 answers; the constraints stay as the final barrier and their known
violations are translated (never a 500):

- libro_autor_pkey          (unique)  -> 409 RELATION_ALREADY_EXISTS
- libro_autor_autor_id_fkey (FK)      -> 404 AUTHOR_NOT_FOUND on insert,
                                         409 AUTHOR_HAS_BOOKS on DELETE autor
- libro_autor_isbn_fkey     (FK)      -> 404 BOOK_NOT_FOUND

No Redis cache is touched: Books only caches /books and /books/<isbn>,
whose payloads do not include authors.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from db.connection import open_connection, transaction
from repositories import author_repository as repo
from utils.errors import (
    author_has_books,
    author_not_found,
    book_not_found,
    relation_already_exists,
    relation_not_found,
)
from utils.validators import is_plausible_isbn


logger = logging.getLogger("authors_microservice.authors")

RELATION_PRIMARY_KEY = "libro_autor_pkey"
RELATION_AUTHOR_FK = "libro_autor_autor_id_fkey"
RELATION_BOOK_FK = "libro_autor_isbn_fkey"


def _constraint_name(exc: psycopg.Error) -> str | None:
    diag = getattr(exc, "diag", None)
    return getattr(diag, "constraint_name", None) if diag is not None else None


def to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "autor_id": row["autor_id"],
        "nombre": row["nombre"],
        "apellido": row["apellido"],
        "pais": row["pais"],
        "books_count": int(row.get("books_count") or 0),
    }


# ---------------------------------------------------------------------------
# Public reads
# ---------------------------------------------------------------------------

def list_authors(limit: int, offset: int, q: str | None) -> tuple[list[dict[str, Any]], int]:
    with open_connection() as conn:
        rows = repo.list_authors(conn, limit, offset, q)
        total = repo.count_authors(conn, q)
    return [to_public(r) for r in rows], total


def get_author(autor_id: int) -> dict[str, Any]:
    with open_connection() as conn:
        row = repo.get_author(conn, autor_id)
    if row is None:
        raise author_not_found()
    return to_public(row)


def list_author_books(autor_id: int) -> dict[str, Any]:
    with open_connection() as conn:
        author = repo.get_author(conn, autor_id)
        if author is None:
            raise author_not_found()
        books = repo.list_author_books(conn, autor_id)
    return {"author": to_public(author), "books": [dict(b) for b in books]}


# ---------------------------------------------------------------------------
# Author writes (ADMIN)
# ---------------------------------------------------------------------------

def create_author(values: dict[str, Any], actor_id: int) -> dict[str, Any]:
    # autores has no UNIQUE besides the PK: two authors with the same name
    # are legitimate (homonyms), so no duplicate rule is invented here.
    with transaction() as conn:
        autor_id = repo.insert_author(conn, values["nombre"], values["apellido"], values["pais"])
        row = repo.get_author(conn, autor_id)
    logger.info("Author %s created by admin %s", autor_id, actor_id)
    return to_public(row)


def update_author(autor_id: int, values: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """PUT and PATCH: `values` only holds validated fields the client sent."""
    with transaction() as conn:
        current = repo.get_author(conn, autor_id, for_update=True)
        if current is None:
            raise author_not_found()

        changes = {k: v for k, v in values.items() if current[k] != v}
        repo.update_author(conn, autor_id, changes)
        row = repo.get_author(conn, autor_id)

    logger.info("Author %s updated by admin %s (fields=%s)", autor_id, actor_id, ",".join(sorted(changes)) or "-")
    return to_public(row)


def delete_author(autor_id: int, actor_id: int) -> None:
    """
    Never deletes books. libro_autor.autor_id is ON DELETE RESTRICT, so an
    author that still has books is refused with 409 (the relations must be
    removed explicitly first). An author without books is deleted.
    """
    with transaction() as conn:
        current = repo.get_author(conn, autor_id, for_update=True)
        if current is None:
            raise author_not_found()

        books_count = int(current.get("books_count") or 0)
        if books_count:
            raise author_has_books(books_count)

        try:
            repo.delete_author(conn, autor_id)
        except psycopg.errors.ForeignKeyViolation as exc:
            # A relation was created concurrently: RESTRICT kept it safe.
            raise author_has_books(1) from exc

    logger.info("Author %s deleted by admin %s", autor_id, actor_id)


# ---------------------------------------------------------------------------
# Author <-> book relations (ADMIN)
# ---------------------------------------------------------------------------

def add_book(autor_id: int, isbn: str, orden: int | None, actor_id: int) -> dict[str, Any]:
    if not is_plausible_isbn(isbn):
        raise book_not_found()

    with transaction() as conn:
        if repo.get_author(conn, autor_id) is None:
            raise author_not_found()
        book = repo.get_book(conn, isbn)
        if book is None:
            raise book_not_found()
        if repo.relation_exists(conn, autor_id, isbn):
            raise relation_already_exists()

        final_orden = orden if orden is not None else repo.next_orden(conn, isbn)
        # If the author or the book is deleted concurrently, the FKs of
        # libro_autor reject the INSERT (mapped to 404 below).
        try:
            repo.insert_relation(conn, autor_id, isbn, final_orden)
        except psycopg.errors.UniqueViolation as exc:
            raise relation_already_exists() from exc
        except psycopg.errors.ForeignKeyViolation as exc:
            if _constraint_name(exc) == RELATION_BOOK_FK:
                raise book_not_found() from exc
            raise author_not_found() from exc

    logger.info("Author %s linked to book %s by admin %s", autor_id, isbn, actor_id)
    return {
        "autor_id": autor_id,
        "isbn": book["isbn"],
        "titulo": book["titulo"],
        "anio_publicacion": book["anio_publicacion"],
        "orden": final_orden,
    }


def remove_book(autor_id: int, isbn: str, actor_id: int) -> None:
    """Deletes only the libro_autor row; the author and the book remain."""
    with transaction() as conn:
        if repo.delete_relation(conn, autor_id, isbn):
            logger.info("Author %s unlinked from book %s by admin %s", autor_id, isbn, actor_id)
            return
        # Nothing deleted: say precisely what is missing.
        if repo.get_author(conn, autor_id) is None:
            raise author_not_found()
        if not is_plausible_isbn(isbn) or repo.get_book(conn, isbn) is None:
            raise book_not_found()
        raise relation_not_found()
