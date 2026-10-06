"""
POST/PUT/PATCH/DELETE /books: JWT (library_shared), ADMIN role, status
codes, PostgreSQL-first ordering and cache invalidation.
"""

import time
import unittest
import xml.etree.ElementTree as ET

from books_fakes import VALID_NEW_BOOK, BooksAppMixin

from library_shared.roles import ROLE_ADMIN, ROLE_USER
from library_shared.token_store import revoke_token


def _warm(test):
    """Fill the list and detail caches so invalidation can be observed."""
    test.client.get("/books")
    test.client.get("/books?q=dune")
    test.client.get("/books/9780000000002")
    test.assertEqual(len(test.redis.keys_with_prefix("books:")), 3)


class AuthenticationTests(BooksAppMixin, unittest.TestCase):
    def test_public_reads_need_no_token(self):
        self.assertEqual(self.client.get("/books").status_code, 200)
        self.assertEqual(self.client.get("/books/9780000000002").status_code, 200)

    def test_post_without_token_is_401(self):
        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK)

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"]["code"], "MISSING_TOKEN")
        self.assertTrue(resp.headers["WWW-Authenticate"].startswith("Bearer"))
        self.assertEqual(self.catalog.calls["create_book"], 0)

    def test_malformed_authorization_header_is_401(self):
        for header in ("Basic abc", "Bearer", "Token abc", "Bearer a b"):
            resp = self.client.post("/books", json=VALID_NEW_BOOK, headers={"Authorization": header})
            self.assertEqual(resp.status_code, 401, header)

    def test_auth_errors_default_to_xml_like_other_catalog_errors(self):
        resp = self.client.delete("/books/9780000000002")

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.mimetype, "application/xml")
        root = ET.fromstring(resp.data)
        self.assertEqual(root.tag, "error")
        self.assertEqual(root.find("code").text, "MISSING_TOKEN")

    def test_expired_token_is_401(self):
        expired = self.access(ROLE_ADMIN, now=int(time.time()) - 3600)

        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=self.bearer(expired))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"]["code"], "TOKEN_EXPIRED")

    def test_revoked_token_is_401(self):
        issued = self.access(ROLE_ADMIN)
        revoke_token(self.gateway, issued.claims)

        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=self.bearer(issued))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"]["code"], "TOKEN_REVOKED")
        self.assertEqual(self.catalog.calls["create_book"], 0)

    def test_refresh_token_cannot_be_used_as_access(self):
        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=self.bearer(self.refresh()))

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"]["code"], "INVALID_TOKEN")

    def test_token_signed_with_another_secret_is_401(self):
        import jwt

        forged = jwt.encode(
            {"user_id": 1, "role_id": ROLE_ADMIN, "jti": "x", "iat": int(time.time()),
             "exp": int(time.time()) + 600, "type": "access"},
            "attacker-secret-key-that-is-long-enough-000",
            algorithm="HS256",
        )

        resp = self.client.post("/books", json=VALID_NEW_BOOK, headers=self.bearer(forged))

        self.assertEqual(resp.status_code, 401)

    def test_user_role_is_403_on_every_write(self):
        headers = self.user_headers()
        calls = [
            self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=headers),
            self.client.put("/books/9780000000002?format=json", json={}, headers=headers),
            self.client.patch("/books/9780000000002?format=json", json={"stock": 1}, headers=headers),
            self.client.delete("/books/9780000000002?format=json", headers=headers),
        ]

        for resp in calls:
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.get_json()["error"]["code"], "FORBIDDEN")
            self.assertNotIn("WWW-Authenticate", resp.headers)
        self.assertEqual(sum(self.catalog.calls[n] for n in ("create_book", "update_book", "delete_book")), 0)

    def test_redis_down_fails_closed_for_writes_but_reads_still_work(self):
        headers = self.admin_headers()
        self.redis.down = True

        write = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=headers)
        read = self.client.get("/books?format=json")

        self.assertEqual(write.status_code, 503)
        self.assertEqual(write.get_json()["error"]["code"], "AUTH_BACKEND_UNAVAILABLE")
        self.assertEqual(self.catalog.calls["create_book"], 0)
        self.assertEqual(read.status_code, 200)


class CreateBookTests(BooksAppMixin, unittest.TestCase):
    def test_admin_creates_book_201(self):
        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertEqual(body["isbn"], "9781234567897")
        self.assertEqual(body["titulo"], "Nuevo libro")  # trimmed
        self.assertEqual(body["precio"], "349.99")
        self.assertEqual(body["categoria"], "Infantil")
        self.assertNotIn("X-Cache-Invalidation", resp.headers)

    def test_created_book_is_xml_by_default(self):
        resp = self.client.post("/books", json=VALID_NEW_BOOK, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(ET.fromstring(resp.data).find("isbn").text, "9781234567897")

    def test_stock_defaults_to_zero_like_the_table(self):
        body = {k: v for k, v in VALID_NEW_BOOK.items() if k != "stock"}

        resp = self.client.post("/books?format=json", json=body, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["stock"], 0)

    def test_duplicate_isbn_is_409(self):
        body = dict(VALID_NEW_BOOK, isbn="9780000000002")

        resp = self.client.post("/books?format=json", json=body, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["error"]["code"], "BOOK_ALREADY_EXISTS")

    def test_unknown_formato_is_400(self):
        resp = self.client.post(
            "/books?format=json", json=dict(VALID_NEW_BOOK, formato_id=99), headers=self.admin_headers()
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "INVALID_REFERENCE")

    def test_invalid_bodies_are_400_and_never_reach_postgresql(self):
        cases = [
            None,
            [],
            {k: v for k, v in VALID_NEW_BOOK.items() if k != "titulo"},
            dict(VALID_NEW_BOOK, isbn="12345"),
            dict(VALID_NEW_BOOK, anio_publicacion=1200),
            dict(VALID_NEW_BOOK, precio="-1"),
            dict(VALID_NEW_BOOK, precio="1.999"),
            dict(VALID_NEW_BOOK, stock=-1),
            dict(VALID_NEW_BOOK, stock=True),
            dict(VALID_NEW_BOOK, titulo="   "),
            dict(VALID_NEW_BOOK, titulo="x" * 301),
            dict(VALID_NEW_BOOK, fecha_creacion="2020-01-01"),
        ]
        for body in cases:
            resp = self.client.post("/books?format=json", json=body, headers=self.admin_headers())
            self.assertEqual(resp.status_code, 400, body)
            self.assertEqual(resp.get_json()["error"]["code"], "INVALID_INPUT")
        self.assertEqual(self.catalog.calls["create_book"], 0)

    def test_non_json_body_is_400(self):
        resp = self.client.post(
            "/books?format=json", data="isbn=1", content_type="text/plain", headers=self.admin_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_post_invalidates_all_list_keys(self):
        _warm(self)

        self.client.post("/books", json=VALID_NEW_BOOK, headers=self.admin_headers())

        self.assertEqual(self.redis.keys_with_prefix("books:list:"), [])
        self.assertEqual(self.redis.keys_with_prefix("books:"), ["books:9780000000002"])
        self.assertEqual(len(self.client.get("/books?format=json").get_json()["books"]), 4)

    def test_post_invalidates_a_cached_not_found(self):
        self.assertEqual(self.client.get("/books/9781234567897").status_code, 404)

        self.client.post("/books", json=VALID_NEW_BOOK, headers=self.admin_headers())

        self.assertEqual(self.client.get("/books/9781234567897").status_code, 200)

    def test_postgresql_failure_is_500_and_cache_is_not_touched(self):
        _warm(self)
        self.catalog.down = True

        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(len(self.redis.keys_with_prefix("books:")), 3)
        self.assertEqual(self.gateway.metrics.get("cache_invalidation"), 0)

    def test_redis_failure_after_commit_keeps_the_write(self):
        headers = self.admin_headers()  # authorization check passes first
        self.redis.fail_deletes = True

        resp = self.client.post("/books?format=json", json=VALID_NEW_BOOK, headers=headers)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.headers["X-Cache-Invalidation"], "failed")
        self.assertIn("9781234567897", self.catalog.rows)
        self.assertEqual(self.gateway.metrics.get("cache_invalidation_failed"), 1)


class UpdateBookTests(BooksAppMixin, unittest.TestCase):
    FULL = {
        "titulo": "Cloud Computing 2nd ed.",
        "anio_publicacion": 2025,
        "precio": 300,
        "stock": 9,
        "formato_id": 2,
        "categoria_id": 2,
    }

    def test_put_replaces_every_field(self):
        resp = self.client.put("/books/9780000000002?format=json", json=self.FULL, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["titulo"], "Cloud Computing 2nd ed.")
        self.assertEqual(body["formato"], "Digital")
        self.assertEqual(body["stock"], 9)

    def test_put_requires_every_field(self):
        partial = {k: v for k, v in self.FULL.items() if k != "stock"}

        resp = self.client.put("/books/9780000000002?format=json", json=partial, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.catalog.calls["update_book"], 0)

    def test_put_cannot_change_the_isbn(self):
        body = dict(self.FULL, isbn="9781234567897")

        resp = self.client.put("/books/9780000000002?format=json", json=body, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 400)

    def test_put_unknown_book_is_404(self):
        resp = self.client.put("/books/9789999999999?format=json", json=self.FULL, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 404)

    def test_patch_updates_only_given_fields(self):
        before = dict(self.catalog.rows["9780000000002"])

        resp = self.client.patch(
            "/books/9780000000002?format=json", json={"precio": "275.5"}, headers=self.admin_headers()
        )

        self.assertEqual(resp.status_code, 200)
        after = self.catalog.rows["9780000000002"]
        self.assertEqual(str(after["precio"]), "275.5")
        for field in ("titulo", "anio_publicacion", "stock", "formato_id", "categoria_id"):
            self.assertEqual(after[field], before[field], field)

    def test_patch_null_is_rejected_not_written(self):
        resp = self.client.patch(
            "/books/9780000000002?format=json", json={"titulo": None}, headers=self.admin_headers()
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.catalog.rows["9780000000002"]["titulo"], "Cloud Computing Basics")

    def test_patch_empty_body_is_400(self):
        resp = self.client.patch("/books/9780000000002?format=json", json={}, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 400)

    def test_patch_unknown_book_is_404(self):
        resp = self.client.patch("/books/9789999999999?format=json", json={"stock": 1}, headers=self.admin_headers())

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"]["code"], "BOOK_NOT_FOUND")

    def test_put_and_patch_invalidate_detail_and_lists(self):
        for method, body in (("put", self.FULL), ("patch", {"stock": 1})):
            _warm(self)
            getattr(self.client, method)("/books/9780000000002", json=body, headers=self.admin_headers())
            self.assertEqual(self.redis.keys_with_prefix("books:"), [], method)

        fresh = self.client.get("/books/9780000000002?format=json").get_json()
        self.assertEqual(fresh["stock"], 1)

    def test_patch_works_through_normalized_isbn(self):
        resp = self.client.patch(
            "/books/%20978-0-306-40615-7%20?format=json", json={"stock": 2}, headers=self.admin_headers()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.catalog.rows["978-0-306-40615-7"]["stock"], 2)


class DeleteBookTests(BooksAppMixin, unittest.TestCase):
    def test_delete_allowed_book(self):
        resp = self.client.delete("/books/9780000000002?format=json", headers=self.admin_headers())

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"deleted": True, "isbn": "9780000000002"})
        self.assertNotIn("9780000000002", self.catalog.rows)

    def test_delete_xml(self):
        resp = self.client.delete("/books/9780000000002", headers=self.admin_headers())

        root = ET.fromstring(resp.data)
        self.assertEqual(root.tag, "deleted")
        self.assertEqual(root.find("deleted").text, "true")

    def test_delete_unknown_book_is_404(self):
        resp = self.client.delete("/books/9789999999999?format=json", headers=self.admin_headers())

        self.assertEqual(resp.status_code, 404)

    def test_delete_book_with_order_history_is_409_and_keeps_it(self):
        _warm(self)

        resp = self.client.delete("/books/9780000000019?format=json", headers=self.admin_headers())

        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["error"]["code"], "BOOK_HAS_ORDER_HISTORY")
        self.assertIn("9780000000019", self.catalog.rows)
        # Nothing changed, so nothing was invalidated.
        self.assertEqual(len(self.redis.keys_with_prefix("books:")), 3)

    def test_delete_invalidates_detail_and_lists(self):
        _warm(self)

        self.client.delete("/books/9780000000002", headers=self.admin_headers())

        self.assertEqual(self.redis.keys_with_prefix("books:"), [])
        self.assertEqual(self.client.get("/books/9780000000002").status_code, 404)

    def test_delete_with_redis_down_during_auth_is_503_and_nothing_is_deleted(self):
        headers = self.admin_headers()
        self.redis.down = True

        resp = self.client.delete("/books/9780000000002?format=json", headers=headers)

        self.assertEqual(resp.status_code, 503)
        self.assertIn("9780000000002", self.catalog.rows)


if __name__ == "__main__":
    unittest.main()
