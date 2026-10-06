"""
Fixtures for the authors microservice tests.

No real PostgreSQL or Redis is used here:
- Redis is an in-memory fake (only what JWT revocation needs) that can be
  switched "down" to simulate an outage.
- The repository functions are replaced by FakeAuthorDb, which reproduces
  the schema rules the service relies on: libro_autor PRIMARY KEY
  (isbn, autor_id), libro_autor.autor_id ON DELETE RESTRICT,
  libro_autor.isbn FK, and transaction rollback on any exception.

tests/test_integration_postgres.py runs the same flows against a REAL
disposable PostgreSQL when AUTHORS_IT_DB_NAME is set.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
import copy
from types import SimpleNamespace

import psycopg
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.redis_client import RedisGateway
from library_shared.settings import load_jwt_settings


JWT_SECRET = "authors-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "redis-test-password"
DB_PASSWORD = "db-test-password"

ADMIN_ID = 1
USER_ID = 2

# Seed: author 1 has two books, author 2 has one, author 3 has none.
BORGES, CORTAZAR, SIN_LIBROS = 1, 2, 3
ISBN_FICCIONES = "9780802130303"
ISBN_ALEPH = "9780142437889"
ISBN_RAYUELA = "9788437604572"
ISBN_HUERFANO = "9780000000002"  # book without authors


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.down = False
        self.calls = 0

    def _check(self) -> None:
        self.calls += 1
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


# ---------------------------------------------------------------------------
# PostgreSQL (repository layer)
# ---------------------------------------------------------------------------

class _ConstraintError:
    """psycopg errors built by hand have no diag; give them the constraint."""

    def __init__(self, message: str, constraint_name: str) -> None:
        super().__init__(message)
        self._constraint = constraint_name

    @property
    def diag(self):
        return SimpleNamespace(constraint_name=self._constraint)


class FakeUniqueViolation(_ConstraintError, psycopg.errors.UniqueViolation):
    pass


class FakeForeignKeyViolation(_ConstraintError, psycopg.errors.ForeignKeyViolation):
    pass


class FakeConnection:
    """Enough of a psycopg connection for `SELECT 1` in /health."""

    def cursor(self):
        return nullcontext(self)

    def execute(self, _sql):
        return None

    def fetchone(self):
        return (1,)


class FakeAuthorDb:
    def __init__(self) -> None:
        self.authors: dict[int, dict] = {}
        self.books: dict[str, dict] = {}
        self.relations: dict[tuple[str, int], int] = {}  # (isbn, autor_id) -> orden
        self.next_id = 1
        self.down = False
        self.rollbacks = 0

    def add_author(self, nombre: str, apellido: str, pais: str | None) -> int:
        autor_id = self.next_id
        self.next_id += 1
        self.authors[autor_id] = {"autor_id": autor_id, "nombre": nombre, "apellido": apellido, "pais": pais}
        return autor_id

    def add_book(self, isbn: str, titulo: str, anio: int = 2000) -> None:
        self.books[isbn] = {"isbn": isbn, "titulo": titulo, "anio_publicacion": anio}

    # -- connection / transaction -------------------------------------------

    def open_connection(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        return nullcontext(FakeConnection())

    @contextmanager
    def transaction(self):
        if self.down:
            raise psycopg.OperationalError(f"connection failed: password={DB_PASSWORD}")
        snapshot = copy.deepcopy((self.authors, self.books, self.relations, self.next_id))
        try:
            yield FakeConnection()
        except BaseException:
            self.authors, self.books, self.relations, self.next_id = snapshot
            self.rollbacks += 1
            raise

    # -- helpers ------------------------------------------------------------

    def _with_count(self, row: dict) -> dict:
        count = sum(1 for (_isbn, autor_id) in self.relations if autor_id == row["autor_id"])
        return {**row, "books_count": count}

    def _matches(self, row: dict, q: str | None) -> bool:
        if not q:
            return True
        q = q.lower()
        full = f"{row['nombre']} {row['apellido']}".lower()
        return q in row["nombre"].lower() or q in row["apellido"].lower() or q in full or q in (row["pais"] or "").lower()

    # -- repository API (same signatures as repositories.author_repository) --

    def list_authors(self, _conn, limit, offset, q):
        rows = sorted(
            (r for r in self.authors.values() if self._matches(r, q)),
            key=lambda r: (r["apellido"], r["nombre"], r["autor_id"]),
        )
        return [self._with_count(r) for r in rows[offset : offset + limit]]

    def count_authors(self, _conn, q):
        return sum(1 for r in self.authors.values() if self._matches(r, q))

    def get_author(self, _conn, autor_id, for_update=False):
        row = self.authors.get(autor_id)
        return self._with_count(row) if row else None

    def insert_author(self, _conn, nombre, apellido, pais):
        return self.add_author(nombre, apellido, pais)

    def update_author(self, _conn, autor_id, changes):
        assert set(changes) <= {"nombre", "apellido", "pais"}
        self.authors[autor_id].update(changes)

    def delete_author(self, _conn, autor_id):
        if any(a == autor_id for (_i, a) in self.relations):
            raise FakeForeignKeyViolation("fk violation", "libro_autor_autor_id_fkey")  # RESTRICT
        self.authors.pop(autor_id, None)

    def list_author_books(self, _conn, autor_id):
        rows = [
            {**self.books[isbn], "orden": orden}
            for (isbn, a), orden in self.relations.items()
            if a == autor_id
        ]
        return sorted(rows, key=lambda r: (r["titulo"], r["isbn"]))

    def get_book(self, _conn, isbn):
        book = self.books.get(isbn)
        return dict(book) if book else None

    def relation_exists(self, _conn, autor_id, isbn):
        return (isbn, autor_id) in self.relations

    def next_orden(self, _conn, isbn):
        return min(max((o for (i, _a), o in self.relations.items() if i == isbn), default=0) + 1, 32767)

    def insert_relation(self, _conn, autor_id, isbn, orden):
        if (isbn, autor_id) in self.relations:
            raise FakeUniqueViolation("duplicate key", "libro_autor_pkey")
        if isbn not in self.books:
            raise FakeForeignKeyViolation("fk violation", "libro_autor_isbn_fkey")
        if autor_id not in self.authors:
            raise FakeForeignKeyViolation("fk violation", "libro_autor_autor_id_fkey")
        self.relations[(isbn, autor_id)] = orden

    def delete_relation(self, _conn, autor_id, isbn):
        return self.relations.pop((isbn, autor_id), None) is not None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def author_db(monkeypatch) -> FakeAuthorDb:
    from repositories import author_repository
    from routes import health
    from services import author_service

    db = FakeAuthorDb()
    db.add_author("Jorge Luis", "Borges", "Argentina")  # 1
    db.add_author("Julio", "Cortázar", "Argentina")  # 2
    db.add_author("Ana", "Sin Libros", None)  # 3
    db.add_book(ISBN_FICCIONES, "Ficciones", 1944)
    db.add_book(ISBN_ALEPH, "El Aleph", 1949)
    db.add_book(ISBN_RAYUELA, "Rayuela", 1963)
    db.add_book(ISBN_HUERFANO, "Libro sin autores", 2001)
    db.relations[(ISBN_FICCIONES, BORGES)] = 1
    db.relations[(ISBN_ALEPH, BORGES)] = 1
    db.relations[(ISBN_RAYUELA, CORTAZAR)] = 1

    monkeypatch.setattr(author_service, "open_connection", db.open_connection)
    monkeypatch.setattr(author_service, "transaction", db.transaction)
    monkeypatch.setattr(health, "open_connection", db.open_connection)
    for name in (
        "list_authors",
        "count_authors",
        "get_author",
        "insert_author",
        "update_author",
        "delete_author",
        "list_author_books",
        "get_book",
        "relation_exists",
        "next_orden",
        "insert_relation",
        "delete_relation",
    ):
        monkeypatch.setattr(author_repository, name, getattr(db, name))
    return db


@pytest.fixture
def app(env, gateway, author_db):
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
