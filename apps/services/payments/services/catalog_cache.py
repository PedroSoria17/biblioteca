"""
Keeps Books' Redis cache coherent with the stock restored by Payments (refunds).

Books caches GET /books and GET /books/<isbn> (keys from library_shared.keys)
and those payloads include `stock`. CLAUDE.md requires dropping
books:<isbn> and books:list:* after any write to libros, so Payments does it
AFTER its transaction commits. Payments itself caches nothing (same module as Orders).

Uses the OPTIONAL gateway operation: it never raises. If Redis fails, the
order stays committed and the stale entries expire with Books' short TTL
(BOOKS_CACHE_TTL_SECONDS, 60 s by default).
"""

from __future__ import annotations

import logging
from typing import Iterable

from flask import current_app
from library_shared import keys
from library_shared.flask_auth import EXTENSION_KEY


logger = logging.getLogger("payments_microservice.catalog_cache")


def invalidate_books(isbns: Iterable[str]) -> bool:
    isbns = sorted(set(isbns))
    if not isbns:
        return True
    gateway = current_app.extensions[EXTENSION_KEY].gateway
    ok = gateway.cache_invalidate(
        keys=tuple(keys.book_key(isbn) for isbn in isbns),
        patterns=(keys.BOOKS_LIST_PATTERN,),
    )
    if not ok:
        logger.warning("Books cache invalidation failed after a committed stock change (%d book(s))", len(isbns))
    return ok
