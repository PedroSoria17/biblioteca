"""
Integration tests against a REAL, DISPOSABLE PostgreSQL database.

Skipped unless AUTHORS_IT_DB_NAME is set. The database name MUST end in
"_test" (enforced below): never point them at library_db. They only create
and remove their own rows (authors with apellido 'IT-...' and the books
listed in IT_ISBNS), but they insert and delete libros rows to do so.

The database must contain the full schema (01_schema.sql, 02 seed for
formatos/categorias, 06, 04, 05, login_microservice.sql, migration 07). See
README.md ("Pruebas de integración").

Redis is NOT real here (in-memory fake from conftest.py); what is verified
for real is the SQL: libro_autor PK, ON DELETE RESTRICT/CASCADE and the
constraint-name -> HTTP code mapping.

Environment:
  AUTHORS_IT_DB_HOST (127.0.0.1), AUTHORS_IT_DB_PORT (5432), AUTHORS_IT_DB_NAME,
  AUTHORS_IT_DB_USER (library_user), AUTHORS_IT_DB_PASSWORD
"""

from __future__ import annotations

import os

import pytest

from conftest import FakeRedis, bearer


IT_DB_NAME = os.getenv("AUTHORS_IT_DB_NAME", "")

pytestmark = pytest.mark.skipif(not IT_DB_NAME, reason="AUTHORS_IT_DB_NAME not set (no disposable PostgreSQL)")

IT_ISBNS = ("9791111111111", "9791111111112", "9791111111113")
MISSING_ISBN = "9791111111119"


def _db_env() -> dict[str, str]:
    if not IT_DB_NAME.endswith("_test"):
        pytest.fail("AUTHORS_IT_DB_NAME must end with '_test': these tests write and delete rows.")
    return {
        "DB_HOST": os.getenv("AUTHORS_IT_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("AUTHORS_IT_DB_PORT", "5432"),
        "DB_NAME": IT_DB_NAME,
        "DB_USER": os.getenv("AUTHORS_IT_DB_USER", "library_user"),
        "DB_PASSWORD": os.getenv("AUTHORS_IT_DB_PASSWORD", ""),
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
        host=db_env["DB_HOST"],
        port=db_env["DB_PORT"],
        dbname=db_env["DB_NAME"],
        user=db_env["DB_USER"],
        password=db_env["DB_PASSWORD"],
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


def _cleanup(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM libro_autor WHERE isbn = ANY(%s)", (list(IT_ISBNS),))
        cur.execute(
            "DELETE FROM libro_autor WHERE autor_id IN (SELECT autor_id FROM autores WHERE apellido LIKE 'IT-%%')"
        )
        cur.execute("DELETE FROM libros WHERE isbn = ANY(%s)", (list(IT_ISBNS),))
        cur.execute("DELETE FROM autores WHERE apellido LIKE 'IT-%%'")


@pytest.fixture
def seed(sql):
    """Authors A (2 books), B (no books); books 1 and 2 linked to A, book 3 free."""
    _cleanup(sql)
    formato_id = _one(sql, "SELECT min(formato_id) FROM formatos")[0]
    categoria_id = _one(sql, "SELECT min(categoria_id) FROM categorias")[0]
    for n, isbn in enumerate(IT_ISBNS, start=1):
        _one(
            sql,
            "INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, formato_id, categoria_id) "
            "VALUES (%s, %s, 2000, 10, 5, %s, %s) RETURNING isbn",
            (isbn, f"IT Libro {n}", formato_id, categoria_id),
        )

    def author(nombre, apellido, pais):
        return _one(
            sql, "INSERT INTO autores (nombre, apellido, pais) VALUES (%s, %s, %s) RETURNING autor_id",
            (nombre, apellido, pais),
        )[0]

    ids = {"a": author("Autora", "IT-Uno", "Chile"), "b": author("Autor", "IT-Dos", None)}
    for isbn in IT_ISBNS[:2]:
        _one(sql, "INSERT INTO libro_autor (isbn, autor_id, orden) VALUES (%s, %s, 1) RETURNING isbn", (isbn, ids["a"]))
    yield ids
    _cleanup(sql)


@pytest.fixture
def it_redis():
    return FakeRedis()


@pytest.fixture
def it_client(db_env, seed, it_redis):
    from app import create_app
    from library_shared.redis_client import RedisGateway

    application = create_app(redis_gateway=RedisGateway(it_redis))
    application.testing = True
    return application.test_client()


@pytest.fixture
def admin_h(make_token):
    return bearer(make_token(1, 2))


def _libros_count(sql) -> int:
    return _one(sql, "SELECT count(*) FROM libros")[0]


def _relation(sql, autor_id, isbn):
    return _one(sql, "SELECT orden FROM libro_autor WHERE autor_id = %s AND isbn = %s", (autor_id, isbn))


# ---------------------------------------------------------------------------


def test_public_reads(it_client, seed):
    body = it_client.get("/authors?q=IT-").get_json()
    assert [a["apellido"] for a in body["data"]] == ["IT-Dos", "IT-Uno"]
    assert body["pagination"]["total"] == 2

    author = it_client.get(f"/authors/{seed['a']}").get_json()["data"]
    assert author == {"autor_id": seed["a"], "nombre": "Autora", "apellido": "IT-Uno", "pais": "Chile", "books_count": 2}

    books = it_client.get(f"/authors/{seed['a']}/books").get_json()["data"]["books"]
    assert [b["isbn"] for b in books] == list(IT_ISBNS[:2])
    assert it_client.get("/authors/999999999").status_code == 404


def test_search_escapes_like_wildcards(it_client):
    assert it_client.get("/authors?q=IT-%25").get_json()["pagination"]["total"] == 0
    assert it_client.get("/authors?q=IT_").get_json()["pagination"]["total"] == 0


def test_public_reads_with_redis_down(it_client, it_redis, seed):
    it_redis.down = True

    assert it_client.get(f"/authors/{seed['a']}/books").status_code == 200
    assert it_client.post("/authors", json={"nombre": "X", "apellido": "IT-X"}, headers=bearer("x")).status_code == 401


def test_create_put_patch(it_client, admin_h, sql):
    created = it_client.post(
        "/authors", json={"nombre": " Nueva ", "apellido": "IT-Tres", "pais": "Perú"}, headers=admin_h
    )
    assert created.status_code == 201
    autor_id = created.get_json()["data"]["autor_id"]
    assert _one(sql, "SELECT nombre, apellido, pais FROM autores WHERE autor_id = %s", (autor_id,)) == (
        "Nueva",
        "IT-Tres",
        "Perú",
    )

    assert it_client.patch(f"/authors/{autor_id}", json={"pais": None}, headers=admin_h).status_code == 200
    assert _one(sql, "SELECT nombre, apellido, pais FROM autores WHERE autor_id = %s", (autor_id,)) == (
        "Nueva",
        "IT-Tres",
        None,
    )

    body = {"nombre": "Otra", "apellido": "IT-Cuatro", "pais": "Bolivia"}
    assert it_client.put(f"/authors/{autor_id}", json=body, headers=admin_h).status_code == 200
    assert _one(sql, "SELECT nombre, apellido, pais FROM autores WHERE autor_id = %s", (autor_id,)) == (
        "Otra",
        "IT-Cuatro",
        "Bolivia",
    )


def test_relation_lifecycle(it_client, admin_h, seed, sql):
    libros_before = _libros_count(sql)

    created = it_client.post(f"/authors/{seed['b']}/books/{IT_ISBNS[0]}", headers=admin_h)
    assert created.status_code == 201
    assert created.get_json()["data"]["orden"] == 2  # appended after author A
    assert _relation(sql, seed["b"], IT_ISBNS[0]) == (2,)

    dup = it_client.post(f"/authors/{seed['b']}/books/{IT_ISBNS[0]}", headers=admin_h)
    assert dup.status_code == 409 and dup.get_json()["code"] == "RELATION_ALREADY_EXISTS"

    removed = it_client.delete(f"/authors/{seed['b']}/books/{IT_ISBNS[0]}", headers=admin_h)
    assert removed.status_code == 200
    assert _relation(sql, seed["b"], IT_ISBNS[0]) is None
    assert _relation(sql, seed["a"], IT_ISBNS[0]) == (1,)
    assert _one(sql, "SELECT count(*) FROM autores WHERE autor_id = %s", (seed["b"],))[0] == 1
    assert _libros_count(sql) == libros_before

    missing = it_client.delete(f"/authors/{seed['b']}/books/{IT_ISBNS[0]}", headers=admin_h)
    assert missing.status_code == 404 and missing.get_json()["code"] == "RELATION_NOT_FOUND"


def test_relation_not_found_cases(it_client, admin_h, seed):
    assert it_client.post(f"/authors/{seed['b']}/books/{MISSING_ISBN}", headers=admin_h).get_json()["code"] == (
        "BOOK_NOT_FOUND"
    )
    assert it_client.post(f"/authors/999999999/books/{IT_ISBNS[2]}", headers=admin_h).get_json()["code"] == (
        "AUTHOR_NOT_FOUND"
    )


def test_constraint_violations_are_mapped(it_client, admin_h, seed, monkeypatch):
    """Skip the explicit checks so the REAL constraints fire."""
    from repositories import author_repository

    monkeypatch.setattr(author_repository, "relation_exists", lambda *_a, **_k: False)
    response = it_client.post(f"/authors/{seed['a']}/books/{IT_ISBNS[0]}", headers=admin_h)
    assert response.status_code == 409
    assert response.get_json()["code"] == "RELATION_ALREADY_EXISTS"  # libro_autor_pkey

    monkeypatch.setattr(
        author_repository,
        "get_book",
        lambda _conn, isbn: {"isbn": isbn, "titulo": "x", "anio_publicacion": 2000},
    )
    response = it_client.post(f"/authors/{seed['b']}/books/{MISSING_ISBN}", headers=admin_h)
    assert response.status_code == 404
    assert response.get_json()["code"] == "BOOK_NOT_FOUND"  # libro_autor_isbn_fkey

    monkeypatch.setattr(
        author_repository,
        "get_author",
        lambda _conn, autor_id, for_update=False: {"autor_id": autor_id, "books_count": 0},
    )
    response = it_client.post(f"/authors/999999999/books/{IT_ISBNS[2]}", headers=admin_h)
    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"  # libro_autor_autor_id_fkey


def test_delete_author_with_books_is_409_even_if_the_check_is_skipped(it_client, admin_h, seed, sql, monkeypatch):
    libros_before = _libros_count(sql)

    response = it_client.delete(f"/authors/{seed['a']}", headers=admin_h)
    assert response.status_code == 409
    assert response.get_json() == {
        "success": False,
        "code": "AUTHOR_HAS_BOOKS",
        "message": "The author is associated with books; remove those associations first.",
        "details": {"books_count": 2},
    }

    from repositories import author_repository

    real_get = author_repository.get_author
    monkeypatch.setattr(
        author_repository,
        "get_author",
        lambda conn, autor_id, for_update=False: {**real_get(conn, autor_id, for_update), "books_count": 0},
    )
    response = it_client.delete(f"/authors/{seed['a']}", headers=admin_h)
    assert response.status_code == 409  # ON DELETE RESTRICT held
    assert response.get_json()["code"] == "AUTHOR_HAS_BOOKS"

    assert _one(sql, "SELECT count(*) FROM autores WHERE autor_id = %s", (seed["a"],))[0] == 1
    assert _one(sql, "SELECT count(*) FROM libro_autor WHERE autor_id = %s", (seed["a"],))[0] == 2
    assert _libros_count(sql) == libros_before


def test_delete_author_after_unlinking_never_deletes_books(it_client, admin_h, seed, sql):
    libros_before = _libros_count(sql)
    for isbn in IT_ISBNS[:2]:
        assert it_client.delete(f"/authors/{seed['a']}/books/{isbn}", headers=admin_h).status_code == 200

    response = it_client.delete(f"/authors/{seed['a']}", headers=admin_h)

    assert response.status_code == 200
    assert _one(sql, "SELECT count(*) FROM autores WHERE autor_id = %s", (seed["a"],))[0] == 0
    assert _libros_count(sql) == libros_before
    assert _one(sql, "SELECT count(*) FROM libros WHERE isbn = ANY(%s)", (list(IT_ISBNS),))[0] == 3


def test_book_deleted_by_books_cascades_only_its_relations(it_client, seed, sql):
    """Documents the existing FK: libro_autor.isbn ON DELETE CASCADE."""
    _one(sql, "DELETE FROM libros WHERE isbn = %s RETURNING isbn", (IT_ISBNS[0],))

    assert _relation(sql, seed["a"], IT_ISBNS[0]) is None
    author = it_client.get(f"/authors/{seed['a']}").get_json()["data"]
    assert author["books_count"] == 1
