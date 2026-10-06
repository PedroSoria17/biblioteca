"""
Cache-aside for the public reads GET /books and GET /books/<isbn>.
PostgreSQL = FakeCatalog, Redis = FakeRedis (see books_fakes.py).
"""

import json
import logging
import unittest
import xml.etree.ElementTree as ET

from books_fakes import REDIS_PASSWORD, BooksAppMixin

from catalog.cache import BooksCache


class BooksListCacheTests(BooksAppMixin, unittest.TestCase):
    def test_first_list_is_a_miss_and_is_cached_with_configured_ttl(self):
        resp = self.client.get("/books?format=json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["books"]), 3)
        self.assertEqual(self.catalog.calls["list_books"], 1)
        self.assertIn("books:list:all", self.redis.store)
        self.assertEqual(self.redis.ttls["books:list:all"], 45)  # BOOKS_CACHE_TTL_SECONDS
        self.assertEqual(self.gateway.metrics.get("cache_miss"), 1)

    def test_second_list_is_a_hit_and_skips_postgresql(self):
        first = self.client.get("/books?format=json")
        second = self.client.get("/books?format=json")

        self.assertEqual(self.catalog.calls["list_books"], 1)
        self.assertEqual(self.gateway.metrics.get("cache_hit"), 1)
        self.assertEqual(first.get_json(), second.get_json())

    def test_hit_and_miss_render_identical_json_and_xml(self):
        miss_json = self.client.get("/books?format=json").data
        hit_json = self.client.get("/books?format=json").data
        hit_xml = self.client.get("/books").data
        self.redis.store.clear()
        miss_xml = self.client.get("/books").data

        self.assertEqual(miss_json, hit_json)
        self.assertEqual(miss_xml, hit_xml)
        root = ET.fromstring(hit_xml)
        self.assertEqual(root.tag, "books")
        self.assertEqual([b.find("precio").text for b in root.findall("book")], ["10.50", "250.00", "199.90"])

    def test_format_is_not_part_of_the_cache_key(self):
        self.client.get("/books?format=json")
        self.client.get("/books?format=xml")

        self.assertEqual(self.catalog.calls["list_books"], 1)
        self.assertEqual(self.redis.keys_with_prefix("books:list:"), ["books:list:all"])

    def test_equivalent_filters_share_one_key(self):
        a = self.client.get("/books?format=json&q=%20Dune%20").get_json()
        b = self.client.get("/books?q=dune&format=json").get_json()
        c = self.client.get("/books?format=json&q=DUNE&ignored=1").get_json()

        self.assertEqual(a, b)
        self.assertEqual(b, c)
        self.assertEqual([book["isbn"] for book in a["books"]], ["9780000000019"])
        self.assertEqual(self.catalog.calls["list_books"], 1)
        self.assertEqual(self.redis.keys_with_prefix("books:list:"), ["books:list:q=dune"])

    def test_list_key_normalization(self):
        self.assertEqual(BooksCache.list_key(None), "books:list:all")
        self.assertEqual(BooksCache.list_key("   "), "books:list:all")
        self.assertEqual(BooksCache.list_key(" Cloud Computing "), "books:list:q=cloud+computing")

    def test_redis_down_list_falls_back_to_postgresql(self):
        self.redis.down = True

        resp = self.client.get("/books?format=json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["books"]), 3)
        self.assertEqual(self.catalog.calls["list_books"], 1)
        self.assertGreaterEqual(self.gateway.metrics.get("redis_error"), 1)

    def test_redis_down_warning_is_logged_without_secrets(self):
        self.redis.down = True

        with self.assertLogs("library_shared.redis", level=logging.WARNING) as logs:
            self.client.get("/books?format=json")

        text = "\n".join(logs.output)
        self.assertIn("cache_get", text)
        self.assertNotIn(REDIS_PASSWORD, text)
        self.assertNotIn("10.0.0.9", text)

    def test_postgresql_down_still_gives_safe_500(self):
        self.catalog.down = True

        resp = self.client.get("/books?format=json")

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"]["code"], "INTERNAL_ERROR")


class BookDetailCacheTests(BooksAppMixin, unittest.TestCase):
    def test_detail_miss_then_hit(self):
        first = self.client.get("/books/9780000000002?format=json")
        second = self.client.get("/books/9780000000002?format=json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), second.get_json())
        self.assertEqual(first.get_json()["precio"], "250.00")
        self.assertEqual(self.catalog.calls["get_book"], 1)
        self.assertEqual(self.redis.ttls["books:9780000000002"], 45)
        cached = json.loads(self.redis.get("books:9780000000002"))
        self.assertEqual(cached["titulo"], "Cloud Computing Basics")

    def test_isbn_is_normalized_like_postgresql(self):
        self.catalog.rows["123456789X"] = dict(self.catalog.rows["9780000000002"], isbn="123456789X")

        resp = self.client.get("/books/%20123456789x%20?format=json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("books:123456789X", self.redis.store)

    def test_hyphenated_isbn_is_kept_as_stored(self):
        resp = self.client.get("/books/978-0-306-40615-7?format=json")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("books:978-0-306-40615-7", self.redis.store)

    def test_unknown_book_is_404(self):
        resp = self.client.get("/books/9789999999999?format=json")

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"]["code"], "BOOK_NOT_FOUND")

    def test_malformed_isbn_is_404_without_touching_postgresql_or_redis(self):
        resp = self.client.get("/books/not-an-isbn")

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.catalog.calls["get_book"], 0)
        self.assertEqual(self.redis.store, {})

    def test_redis_down_detail_falls_back_to_postgresql(self):
        self.redis.down = True

        resp = self.client.get("/books/9780000000002")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ET.fromstring(resp.data).find("titulo").text, "Cloud Computing Basics")

    def test_redis_down_unknown_book_is_still_404(self):
        self.redis.down = True

        self.assertEqual(self.client.get("/books/9789999999999").status_code, 404)


class CacheCooldownTests(BooksAppMixin, unittest.TestCase):
    cache_cooldown_seconds = 60.0

    def test_after_a_redis_failure_reads_skip_the_cache(self):
        self.redis.down = True

        for _ in range(3):
            self.assertEqual(self.client.get("/books?format=json").status_code, 200)

        # Only the first request paid a Redis attempt; the others went
        # straight to PostgreSQL.
        self.assertEqual(self.gateway.metrics.get("redis_error"), 1)
        self.assertGreaterEqual(self.gateway.metrics.get("cache_skipped"), 4)
        self.assertEqual(self.catalog.calls["list_books"], 3)


if __name__ == "__main__":
    unittest.main()
