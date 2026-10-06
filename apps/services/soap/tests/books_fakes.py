"""
Test doubles for the Books REST tests (not collected as tests: no test_
prefix). PostgreSQL is replaced at the catalog.repository boundary and
Redis at the redis-py client boundary, so the real Flask app, library_shared
(JWT, revocation, RedisGateway, cached_json) and catalog/cache.py all run.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import fnmatch
import os
import time
from unittest import mock

from redis.exceptions import ConnectionError as RedisConnectionError

from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.redis_client import RedisGateway
from library_shared.roles import ROLE_ADMIN, ROLE_USER
from library_shared.settings import load_jwt_settings

from catalog import repository
from catalog.errors import book_already_exists, book_has_order_history, invalid_reference


JWT_SECRET = "books-tests-secret-key-long-enough-0123456789abcdef"
REDIS_PASSWORD = "books-redis-test-password"

TEST_ENV = {
    "PGHOST": "127.0.0.1",
    "PGPORT": "59999",
    "PGDATABASE": "library_db_test",
    "PGUSER": "library_soap_user",
    "PGPASSWORD": "pg-test-password",
    "JWT_SECRET_KEY": JWT_SECRET,
    "JWT_ACCESS_TTL_MINUTES": "20",
    "JWT_REFRESH_TTL_DAYS": "7",
    "REDIS_URL": f"redis://:{REDIS_PASSWORD}@127.0.0.1:6399/0",
    "BOOKS_CACHE_TTL_SECONDS": "45",
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    "APP_ENV": "development",
}


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float | None]] = {}
        self.ttls: dict[str, int] = {}
        self.down = False
        self.fail_deletes = False

    def _check(self) -> None:
        if self.down:
            raise RedisConnectionError(f"Error connecting to :{REDIS_PASSWORD}@10.0.0.9:6379")

    def _alive(self, key: str) -> bool:
        item = self.store.get(key)
        if item is None:
            return False
        if item[1] is not None and item[1] <= time.time():
            del self.store[key]
            return False
        return True

    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        return self.store[key][0] if self._alive(key) else None

    def set(self, key, value, ex=None):
        self._check()
        self.store[key] = (value, time.time() + ex if ex else None)
        self.ttls[key] = ex
        return True

    def exists(self, *keys):
        self._check()
        return sum(1 for k in keys if self._alive(k))

    def delete(self, *keys):
        self._check()
        if self.fail_deletes:
            raise RedisConnectionError("connection lost")
        removed = 0
        for k in keys:
            if self._alive(k):
                del self.store[k]
                removed += 1
        return removed

    def scan_iter(self, match="*", count=None):
        self._check()
        if self.fail_deletes:
            raise RedisConnectionError("connection lost")
        return [k for k in list(self.store) if fnmatch.fnmatchcase(k, match) and self._alive(k)]

    def keys_with_prefix(self, prefix: str) -> list[str]:
        return sorted(k for k in self.store if k.startswith(prefix) and self._alive(k))


FORMATOS = {1: "Tapa dura", 2: "Digital"}
CATEGORIAS = {1: "Academico", 2: "Infantil"}


def _book(isbn, titulo, precio, stock=5, formato_id=1, categoria_id=1, anio=2020):
    return {
        "isbn": isbn,
        "titulo": titulo,
        "anio_publicacion": anio,
        "precio": Decimal(precio),
        "stock": stock,
        "formato_id": formato_id,
        "categoria_id": categoria_id,
    }


class FakeCatalog:
    """
    In-memory stand-in for the catalog.repository functions, honoring the
    same contract (None/False when missing, CatalogError on conflicts).
    """

    def __init__(self) -> None:
        self.rows = {
            "9780000000002": _book("9780000000002", "Cloud Computing Basics", "250.00"),
            "9780000000019": _book("9780000000019", "Dune", "199.90", formato_id=2),
            "978-0-306-40615-7": _book("978-0-306-40615-7", "Hyphenated ISBN", "10.50"),
        }
        self.sold = {"9780000000019"}  # referenced by pedido_detalle
        self.calls = {"list_books": 0, "get_book": 0, "create_book": 0, "update_book": 0, "delete_book": 0}
        self.down = False

    def _guard(self, name):
        self.calls[name] += 1
        if self.down:
            raise OSError("could not connect to server")

    def _public(self, row):
        return {
            "isbn": row["isbn"],
            "titulo": row["titulo"],
            "anio_publicacion": row["anio_publicacion"],
            "precio": row["precio"],
            "stock": row["stock"],
            "categoria": CATEGORIAS[row["categoria_id"]],
            "formato": FORMATOS[row["formato_id"]],
        }

    def list_books(self, search=None):
        self._guard("list_books")
        rows = sorted(self.rows.values(), key=lambda r: r["isbn"])
        if search:
            rows = [r for r in rows if search.lower() in r["titulo"].lower() or search.lower() in r["isbn"].lower()]
        return [self._public(r) for r in rows]

    def get_book(self, isbn):
        self._guard("get_book")
        row = self.rows.get(isbn)
        return self._public(row) if row else None

    def _check_refs(self, values):
        if values.get("formato_id", 1) not in FORMATOS or values.get("categoria_id", 1) not in CATEGORIAS:
            raise invalid_reference()

    def create_book(self, isbn, values):
        self._guard("create_book")
        if isbn in self.rows:
            raise book_already_exists()
        self._check_refs(values)
        self.rows[isbn] = {"isbn": isbn, **deepcopy(values)}
        return self._public(self.rows[isbn])

    def update_book(self, isbn, values):
        self._guard("update_book")
        if isbn not in self.rows:
            return None
        self._check_refs(values)
        self.rows[isbn].update(deepcopy(values))
        return self._public(self.rows[isbn])

    def delete_book(self, isbn):
        self._guard("delete_book")
        if isbn not in self.rows:
            return False
        if isbn in self.sold:
            raise book_has_order_history()
        del self.rows[isbn]
        return True


class BooksAppMixin:
    """setUp helper: env, fakes, patched repository, app and token factory."""

    cache_cooldown_seconds = 0.0

    def setUp(self):
        env_patch = mock.patch.dict(os.environ, TEST_ENV)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.catalog = FakeCatalog()
        for name in ("list_books", "get_book", "create_book", "update_book", "delete_book"):
            patcher = mock.patch.object(repository, name, getattr(self.catalog, name))
            patcher.start()
            self.addCleanup(patcher.stop)

        from app import create_app

        self.redis = FakeRedis()
        self.gateway = RedisGateway(self.redis, cache_cooldown_seconds=self.cache_cooldown_seconds)
        self.app = create_app(redis_gateway=self.gateway)
        self.app.testing = True
        self.client = self.app.test_client()
        self.jwt_settings = load_jwt_settings(TEST_ENV)

    def access(self, role_id=ROLE_ADMIN, user_id=1, **kwargs):
        return create_access_token(self.jwt_settings, user_id, role_id, session_id="sid-test", **kwargs)

    def refresh(self, role_id=ROLE_ADMIN):
        return create_refresh_token(self.jwt_settings, 1, role_id, session_id="sid-test")

    @staticmethod
    def bearer(issued):
        token = issued.token if hasattr(issued, "token") else issued
        return {"Authorization": f"Bearer {token}"}

    def admin_headers(self):
        return self.bearer(self.access(ROLE_ADMIN))

    def user_headers(self):
        return self.bearer(self.access(ROLE_USER, user_id=2))


VALID_NEW_BOOK = {
    "isbn": "9781234567897",
    "titulo": "  Nuevo libro  ",
    "anio_publicacion": 2024,
    "precio": "349.99",
    "stock": 3,
    "formato_id": 1,
    "categoria_id": 2,
}
