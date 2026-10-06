"""
Cache-aside for the public catalog reads (GET /books, GET /books/<isbn>).

Built only on library_shared (RedisGateway optional cache_* operations,
cached_json, key conventions). Redis is an optimization here:

- read: Redis HIT -> answer from Redis; MISS -> PostgreSQL, then cache with
  BOOKS_CACHE_TTL_SECONDS; Redis down -> warning (logged by the gateway,
  without host/password) and PostgreSQL answers. Never a 503 because of
  the cache.
- write: called only AFTER PostgreSQL committed. Drops books:<isbn> and
  every books:list:* (SCAN, never KEYS). If Redis fails here the write is
  NOT undone: the stale entry expires with the short TTL.
"""

from __future__ import annotations

import logging
from typing import Any

from library_shared import keys
from library_shared.cache import cached_json
from library_shared.redis_client import RedisGateway

from catalog import repository


logger = logging.getLogger("library_soap_service.cache")


class BooksCache:
    def __init__(self, gateway: RedisGateway, ttl_seconds: int) -> None:
        self.gateway = gateway
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def list_key(search: str | None) -> str:
        # The search is case-insensitive (ILIKE), so "Dune" and " dune "
        # are the same query and must share one entry.
        normalized = (search or "").strip().lower()
        return keys.books_list_key({"q": normalized} if normalized else None)

    def list_books(self, search: str | None) -> list[dict[str, Any]]:
        normalized = (search or "").strip().lower() or None
        return cached_json(
            self.gateway,
            self.list_key(normalized),
            self.ttl_seconds,
            lambda: [repository.to_cacheable(b) for b in repository.list_books(normalized)],
        )

    def get_book(self, isbn: str) -> dict[str, Any] | None:
        """
        A cached `null` (book not found) is allowed on purpose: it is
        bounded by the TTL and dropped by the invalidation after a POST.
        """
        def load():
            book = repository.get_book(isbn)
            return repository.to_cacheable(book) if book is not None else None

        return cached_json(self.gateway, keys.book_key(isbn), self.ttl_seconds, load)

    def invalidate(self, isbn: str) -> bool:
        ok = self.gateway.cache_invalidate(
            keys=(keys.book_key(isbn),),
            patterns=(keys.BOOKS_LIST_PATTERN,),
        )
        if not ok:
            logger.warning(
                "Cache invalidation failed after a committed write (isbn=%s); "
                "stale entries expire within %ss",
                isbn,
                self.ttl_seconds,
            )
        return ok
