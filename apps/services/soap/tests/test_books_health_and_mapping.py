"""
/health?details=true, CORS, required configuration, SOAP still routed, and
the PostgreSQL error -> HTTP mapping of the write repository.
"""

import os
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from psycopg2 import errors as pg_errors

from books_fakes import REDIS_PASSWORD, TEST_ENV, BooksAppMixin

import app as app_module
from catalog import repository
from catalog.errors import CatalogError


class HealthDetailsTests(BooksAppMixin, unittest.TestCase):
    def _db(self, status):
        patcher = mock.patch.object(app_module, "_database_status", return_value=status)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_plain_health_is_unchanged(self):
        resp = self.client.get("/health?format=json")

        self.assertEqual(resp.get_json(), {"status": "ok", "service": "library_soap_service"})

    def test_details_all_up(self):
        self._db("connected")

        resp = self.client.get("/health?format=json&details=true")

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "connected")
        self.assertEqual(body["redis"], "connected")
        self.assertEqual(body["cache"], "enabled")
        self.assertIsInstance(body["metrics"], dict)

    def test_details_redis_down_is_degraded_but_200(self):
        self._db("connected")
        self.redis.down = True

        resp = self.client.get("/health?format=json&details=true")

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["redis"], "unavailable")
        self.assertEqual(body["cache"], "bypassed")
        self.assertNotIn(REDIS_PASSWORD, resp.get_data(as_text=True))
        self.assertNotIn("6399", resp.get_data(as_text=True))
        self.assertNotIn(TEST_ENV["JWT_SECRET_KEY"], resp.get_data(as_text=True))

    def test_details_database_down_is_503(self):
        self._db("unavailable")

        resp = self.client.get("/health?details=true")

        self.assertEqual(resp.status_code, 503)
        root = ET.fromstring(resp.data)
        self.assertEqual(root.find("status").text, "unavailable")
        self.assertEqual(root.find("database").text, "unavailable")
        self.assertIsNotNone(root.find("metrics"))

    def test_database_status_hides_driver_errors(self):
        # Real check against the unreachable PG* from TEST_ENV.
        self.assertEqual(app_module._database_status(), "unavailable")


class AppWiringTests(BooksAppMixin, unittest.TestCase):
    def test_soap_and_wsdl_are_still_served(self):
        self.assertEqual(self.client.post("/soap", data=b"x", content_type="text/plain").status_code, 415)
        self.assertEqual(self.client.get("/wsdl/library-classifier.wsdl").status_code, 200)

    def test_soap_fault_still_returned_for_bad_envelope(self):
        resp = self.client.post("/soap", data=b"<not-soap/>", content_type="text/xml")

        self.assertIn(resp.status_code, (400, 500))
        self.assertIn(b"Fault", resp.data)

    def test_cors_only_for_configured_origin(self):
        allowed = self.client.get("/books", headers={"Origin": "http://localhost:3000"})
        denied = self.client.get("/books", headers={"Origin": "http://evil.example"})

        self.assertEqual(allowed.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000")
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_existing_read_endpoints_are_still_public(self):
        with mock.patch.object(repository, "list_books_with_images", return_value=[]), mock.patch.object(
            repository, "list_cloud_concepts", return_value=[]
        ):
            self.assertEqual(self.client.get("/books-with-images").status_code, 200)
            self.assertEqual(self.client.get("/cloud-concepts").status_code, 200)


class RequiredConfigurationTests(unittest.TestCase):
    def test_missing_jwt_secret_or_redis_url_refuses_to_start(self):
        from app import create_app
        from config.settings import ConfigurationError

        for missing in ("JWT_SECRET_KEY", "REDIS_URL"):
            env = {k: v for k, v in TEST_ENV.items() if k != missing}
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ConfigurationError, msg=missing):
                    create_app()

    def test_cors_wildcard_rejected_in_production(self):
        from app import create_app
        from config.settings import ConfigurationError

        env = dict(TEST_ENV, APP_ENV="production", CORS_ALLOWED_ORIGINS="*")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigurationError):
                create_app()


class _FakeCursor:
    def __init__(self, exc):
        self.exc = exc
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *_args):
        raise self.exc


class _FakeConnection:
    def __init__(self, exc):
        self.exc = exc

    def cursor(self):
        return _FakeCursor(self.exc)


def _fk_violation(constraint):
    # psycopg2 exposes diag read-only; a subclass attribute lets the test
    # control constraint_name exactly as PostgreSQL would report it.
    class _FK(pg_errors.ForeignKeyViolation):
        diag = type("Diag", (), {"constraint_name": constraint})()

    return _FK()


class RepositoryErrorMappingTests(unittest.TestCase):
    def _patch_transaction(self, exc):
        from contextlib import contextmanager

        @contextmanager
        def fake_transaction():
            yield _FakeConnection(exc)

        patcher = mock.patch.object(repository, "transaction", fake_transaction)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _assert_catalog_error(self, func, code, status):
        with self.assertRaises(CatalogError) as ctx:
            func()
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(ctx.exception.http_status, status)

    def test_unique_violation_on_insert_is_409(self):
        self._patch_transaction(pg_errors.UniqueViolation())
        self._assert_catalog_error(lambda: repository.create_book("9781234567897", {"titulo": "x"}), "BOOK_ALREADY_EXISTS", 409)

    def test_foreign_key_on_insert_or_update_is_400(self):
        self._patch_transaction(_fk_violation("libros_formato_id_fkey"))
        self._assert_catalog_error(lambda: repository.update_book("9781234567897", {"formato_id": 9}), "INVALID_REFERENCE", 400)

    def test_check_violation_is_400(self):
        self._patch_transaction(pg_errors.CheckViolation())
        self._assert_catalog_error(lambda: repository.create_book("9781234567897", {"titulo": "x"}), "INVALID_INPUT", 400)

    def test_delete_blocked_by_order_history_is_409(self):
        self._patch_transaction(_fk_violation("fk_pedido_detalle_libro"))
        self._assert_catalog_error(lambda: repository.delete_book("9781234567897"), "BOOK_HAS_ORDER_HISTORY", 409)

    def test_delete_blocked_by_other_reference_is_409(self):
        self._patch_transaction(_fk_violation("some_other_fk"))
        self._assert_catalog_error(lambda: repository.delete_book("9781234567897"), "BOOK_IN_USE", 409)

    def test_unexpected_database_error_is_not_masked(self):
        self._patch_transaction(pg_errors.InsufficientPrivilege())
        with self.assertRaises(pg_errors.InsufficientPrivilege):
            repository.create_book("9781234567897", {"titulo": "x"})

    def test_escape_like(self):
        self.assertEqual(repository._escape_like("50%_off\\"), "50\\%\\_off\\\\")


if __name__ == "__main__":
    unittest.main()
