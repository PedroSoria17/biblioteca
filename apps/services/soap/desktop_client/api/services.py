"""
One small client per microservice. They only know paths and bodies (the
contracts documented in each service's README); HTTP, tokens, refresh and
errors are handled by api.http.ApiClient.

Business rules stay in the backend: these classes never compute prices,
totals, owners or states.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.http import ApiClient, ApiError
from api.session import Session


def _seg(value: Any) -> str:
    """A safe URL path segment (ISBNs may contain '-' or 'X')."""
    return quote(str(value).strip(), safe="")


class AuthApi:
    """Login :5001 (JSON via ?format=json)."""

    def __init__(self, client: ApiClient, session: Session) -> None:
        self.client = client
        self.session = session

    def login(self, email: str, password: str):
        data = self.client.post("login", "/login", json_body={"email": email, "password": password}, auth=False)
        if not isinstance(data, dict) or not data.get("access_token") or not data.get("refresh_token"):
            raise ApiError(None, "INVALID_RESPONSE", "Login did not return tokens.", "login")
        self.session.start(data["access_token"], data["refresh_token"], data["user"])
        return self.session.user

    def logout(self) -> None:
        """
        Revokes the session in the backend when possible; the LOCAL session is
        cleared ALWAYS (network error, expired token, Login down...).
        """
        token = self.session.access_token
        try:
            if token:
                self.client.request("login", "POST", "/logout", auth=False, bearer=token)
        except ApiError:
            pass
        finally:
            self.session.clear()


class BooksApi:
    """Books :5000. Public reads; POST/PATCH/DELETE need ADMIN."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def list(self, q: str | None = None) -> list[dict]:
        return self.client.get("books", "/books", params={"q": q}, auth=False)["books"]

    def get(self, isbn: str) -> dict:
        return self.client.get("books", f"/books/{_seg(isbn)}", auth=False)

    def create(self, values: dict) -> dict:
        return self.client.post("books", "/books", json_body=values)

    def update(self, isbn: str, changes: dict) -> dict:
        return self.client.patch("books", f"/books/{_seg(isbn)}", json_body=changes)

    def delete(self, isbn: str) -> dict:
        return self.client.delete("books", f"/books/{_seg(isbn)}")


class UsersApi:
    """Users :5002 (ADMIN, except /users/me)."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def list(self, limit: int = 200, offset: int = 0) -> dict:
        return self.client.get("users", "/users", params={"limit": limit, "offset": offset})

    def me(self) -> dict:
        return self.client.get("users", "/users/me")["data"]

    def create(self, values: dict) -> dict:
        return self.client.post("users", "/users", json_body=values)["data"]

    def update(self, usuario_id: int, changes: dict) -> dict:
        return self.client.patch("users", f"/users/{int(usuario_id)}", json_body=changes)["data"]

    def change_password(self, usuario_id: int, password: str) -> dict:
        return self.update(usuario_id, {"password": password})

    def delete(self, usuario_id: int) -> dict:
        return self.client.delete("users", f"/users/{int(usuario_id)}")["data"]


class AuthorsApi:
    """Authors :5003. Public reads; writes and relations need ADMIN."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def list(self, q: str | None = None, limit: int = 200, offset: int = 0) -> dict:
        return self.client.get("authors", "/authors", params={"q": q, "limit": limit, "offset": offset}, auth=False)

    def get(self, autor_id: int) -> dict:
        return self.client.get("authors", f"/authors/{int(autor_id)}", auth=False)["data"]

    def books(self, autor_id: int) -> dict:
        return self.client.get("authors", f"/authors/{int(autor_id)}/books", auth=False)["data"]

    def create(self, values: dict) -> dict:
        return self.client.post("authors", "/authors", json_body=values)["data"]

    def update(self, autor_id: int, changes: dict) -> dict:
        return self.client.patch("authors", f"/authors/{int(autor_id)}", json_body=changes)["data"]

    def delete(self, autor_id: int) -> dict:
        return self.client.delete("authors", f"/authors/{int(autor_id)}")["data"]

    def link_book(self, autor_id: int, isbn: str, orden: int | None = None) -> dict:
        body = {"orden": orden} if orden is not None else None
        return self.client.post("authors", f"/authors/{int(autor_id)}/books/{_seg(isbn)}", json_body=body)["data"]

    def unlink_book(self, autor_id: int, isbn: str) -> dict:
        return self.client.delete("authors", f"/authors/{int(autor_id)}/books/{_seg(isbn)}")["data"]


class OrdersApi:
    """Orders :5004. The owner always comes from the token."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def mine(self, estado: str | None = None, limit: int = 200) -> dict:
        return self.client.get("orders", "/orders/me", params={"estado": estado, "limit": limit})

    def list_all(self, estado=None, usuario_id=None, desde=None, hasta=None, limit: int = 200, offset: int = 0) -> dict:
        params = {"estado": estado, "usuario_id": usuario_id, "desde": desde, "hasta": hasta, "limit": limit, "offset": offset}
        return self.client.get("orders", "/orders", params=params)

    def get(self, pedido_id: int) -> dict:
        return self.client.get("orders", f"/orders/{int(pedido_id)}")["data"]

    def items(self, pedido_id: int) -> dict:
        return self.client.get("orders", f"/orders/{int(pedido_id)}/items")["data"]

    def create(self, lines: list[dict]) -> dict:
        """lines: [{"isbn", "cantidad"}]. Never sends prices, totals or usuario_id."""
        items = [{"isbn": line["isbn"], "cantidad": int(line["cantidad"])} for line in lines]
        return self.client.post("orders", "/orders", json_body={"items": items})["data"]

    def set_status(self, pedido_id: int, estado: str) -> dict:
        return self.client.patch("orders", f"/orders/{int(pedido_id)}/status", json_body={"estado": estado})["data"]


class PaymentsApi:
    """Payments :5005. The amount is always the order total (server side)."""

    METHODS = ("credit_card", "debit_card", "bank_transfer", "cash")

    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def mine(self, estado: str | None = None, limit: int = 200) -> dict:
        return self.client.get("payments", "/payments/me", params={"estado": estado, "limit": limit})

    def list_all(self, estado=None, pedido_id=None, metodo_pago=None, limit: int = 200, offset: int = 0) -> dict:
        params = {"estado": estado, "pedido_id": pedido_id, "metodo_pago": metodo_pago, "limit": limit, "offset": offset}
        return self.client.get("payments", "/payments", params=params)

    def get(self, pago_id: int) -> dict:
        return self.client.get("payments", f"/payments/{int(pago_id)}")["data"]

    def for_order(self, pedido_id: int) -> dict:
        return self.client.get("payments", f"/orders/{int(pedido_id)}/payments")["data"]

    def create(self, pedido_id: int, metodo_pago: str, referencia: str | None = None) -> dict:
        body = {"pedido_id": int(pedido_id), "metodo_pago": metodo_pago}
        if referencia:
            body["referencia"] = referencia
        return self.client.post("payments", "/payments", json_body=body)["data"]

    def approve(self, pago_id: int) -> dict:
        return self.client.post("payments", f"/payments/{int(pago_id)}/approve")["data"]

    def reject(self, pago_id: int) -> dict:
        return self.client.post("payments", f"/payments/{int(pago_id)}/reject")["data"]

    def refund(self, pago_id: int) -> dict:
        return self.client.post("payments", f"/payments/{int(pago_id)}/refund")["data"]
