"""
HTTP access to the six Library microservices (no Tkinter here, so it can be
tested without a display). The desktop client never talks to PostgreSQL or
Redis directly.
"""

from __future__ import annotations

from typing import Callable

from api.health import HealthApi
from api.http import ApiClient, Transport
from api.services import AuthApi, AuthorsApi, BooksApi, OrdersApi, PaymentsApi, UsersApi
from api.session import Session


class LibraryApi:
    def __init__(
        self,
        config,
        *,
        transport: Transport | None = None,
        on_session_expired: Callable[[], None] | None = None,
    ) -> None:
        self.session = Session()
        self.client = ApiClient(
            self.session,
            config.base_urls,
            timeout=config.http_timeout,
            transport=transport,
            on_session_expired=on_session_expired,
        )
        self.auth = AuthApi(self.client, self.session)
        self.books = BooksApi(self.client)
        self.users = UsersApi(self.client)
        self.authors = AuthorsApi(self.client)
        self.orders = OrdersApi(self.client)
        self.payments = PaymentsApi(self.client)
        self.health = HealthApi(self.client, timeout=config.health_timeout)
