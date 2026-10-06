"""Paths, methods and bodies sent to each microservice (contracts)."""

from __future__ import annotations

import unittest

from api.errors import friendly_message
from api.http import ApiError
from fakes import err, logged_in, ok


def data(payload):
    return ok({"success": True, "data": payload})


class BooksTests(unittest.TestCase):
    def test_list_and_search(self):
        api, transport = logged_in()
        transport.on("GET", "/books", ok({"books": [{"isbn": "1", "stock": 3}]}))

        books = api.books.list("dune")

        self.assertEqual(books, [{"isbn": "1", "stock": 3}])
        self.assertEqual(transport.calls[0].query, {"q": "dune", "format": "json"})
        self.assertTrue(transport.calls[0].base.endswith(":5000"))

    def test_admin_crud(self):
        api, transport = logged_in(role_id=2)
        transport.on("POST", "/books", ok({"isbn": "9780000000001"}, 201))
        transport.on("PATCH", "/books/978-0-13-468599-1", ok({"isbn": "978-0-13-468599-1"}))
        transport.on("DELETE", "/books/9780000000001", ok({"deleted": True}))

        api.books.create({"isbn": "9780000000001", "titulo": "T", "anio_publicacion": 2000,
                          "precio": "10.00", "formato_id": 1, "categoria_id": 1})
        api.books.update("978-0-13-468599-1", {"stock": 4})
        api.books.delete("9780000000001")

        self.assertEqual(transport.paths(), ["POST /books", "PATCH /books/978-0-13-468599-1", "DELETE /books/9780000000001"])
        self.assertEqual(transport.calls[1].json, {"stock": 4})
        self.assertTrue(all(c.bearer == "access-1" for c in transport.calls))


class UsersTests(unittest.TestCase):
    def test_admin_crud_and_password(self):
        api, transport = logged_in(role_id=2)
        transport.on("GET", "/users", ok({"success": True, "data": [{"usuario_id": 2}], "pagination": {"total": 1}}))
        transport.on("POST", "/users", data({"usuario_id": 5}))
        transport.on("PATCH", "/users/5", data({"usuario_id": 5}))
        transport.on("DELETE", "/users/5", data({"deleted": True}))

        api.users.list()
        api.users.create({"nombre_completo": "N", "email": "n@example.com", "password": "Password1", "role_id": 1, "activo": True})
        api.users.update(5, {"activo": False})
        api.users.change_password(5, "NuevaClave1")
        api.users.delete(5)

        self.assertEqual(transport.calls[0].query, {"limit": "200", "offset": "0"})
        self.assertEqual(transport.calls[2].json, {"activo": False})
        self.assertEqual(transport.calls[3].json, {"password": "NuevaClave1"})
        self.assertTrue(transport.calls[0].base.endswith(":5002"))

    def test_business_errors_have_friendly_messages(self):
        for code, fragment in [
            ("EMAIL_ALREADY_EXISTS", "correo"),
            ("LAST_ADMIN_REQUIRED", "administrador activo"),
            ("ADMIN_ALREADY_EXISTS", "Solo se permite uno"),
            ("USER_HAS_ORDER_HISTORY", "Desactívalo"),
        ]:
            self.assertIn(fragment, friendly_message(ApiError(409, code, "x", "users")))


class AuthorsTests(unittest.TestCase):
    def test_reads_are_public(self):
        api, transport = logged_in()
        transport.on("GET", "/authors", ok({"success": True, "data": [], "pagination": {}}))
        transport.on("GET", "/authors/3/books", data({"author": {}, "books": []}))

        api.authors.list(q="borges")
        api.authors.books(3)

        self.assertEqual(transport.calls[0].query["q"], "borges")
        self.assertTrue(all(c.bearer is None for c in transport.calls))

    def test_relations(self):
        api, transport = logged_in(role_id=2)
        transport.on("POST", "/authors/3/books/9780000000001", data({"orden": 2}))
        transport.on("DELETE", "/authors/3/books/9780000000001", data({"deleted": True}))

        api.authors.link_book(3, " 9780000000001 ")
        api.authors.link_book(3, "9780000000001", orden=4)
        api.authors.unlink_book(3, "9780000000001")

        self.assertIsNone(transport.calls[0].json)
        self.assertEqual(transport.calls[1].json, {"orden": 4})
        self.assertEqual(transport.calls[2].method, "DELETE")

    def test_author_has_books_message(self):
        error = ApiError(409, "AUTHOR_HAS_BOOKS", "x", "authors", {"books_count": 2})
        self.assertEqual(
            friendly_message(error),
            "El autor tiene libros asociados. Elimina primero las relaciones. (libros asociados: 2)",
        )


class OrdersTests(unittest.TestCase):
    def test_create_sends_only_isbn_and_cantidad(self):
        api, transport = logged_in()
        transport.on("POST", "/orders", data({"pedido_id": 1, "estado": "pending", "total": "21.00"}))

        order = api.orders.create([{"isbn": "9780000000001", "cantidad": 2, "titulo": "ignored", "precio": "1"}])

        self.assertEqual(order["pedido_id"], 1)
        self.assertEqual(transport.calls[0].json, {"items": [{"isbn": "9780000000001", "cantidad": 2}]})

    def test_mine_items_and_admin_status(self):
        api, transport = logged_in(role_id=2)
        transport.on("GET", "/orders/me", ok({"success": True, "data": []}))
        transport.on("GET", "/orders/4/items", data({"order": {}, "items": []}))
        transport.on("GET", "/orders", ok({"success": True, "data": []}))
        transport.on("PATCH", "/orders/4/status", data({"estado": "cancelled"}))

        api.orders.mine(estado="pending")
        api.orders.items(4)
        api.orders.list_all(estado="paid", usuario_id=2, desde="2026-10-01")
        api.orders.set_status(4, "cancelled")

        self.assertEqual(transport.calls[0].query, {"estado": "pending", "limit": "200"})
        self.assertEqual(transport.calls[2].query, {"estado": "paid", "usuario_id": "2", "desde": "2026-10-01",
                                                    "limit": "200", "offset": "0"})
        self.assertEqual(transport.calls[3].json, {"estado": "cancelled"})

    def test_insufficient_stock_message_lists_books(self):
        api, transport = logged_in()
        transport.on("POST", "/orders", err(409, "INSUFFICIENT_STOCK", "x",
                                             {"items": [{"isbn": "978A", "requested": 3, "available": 1}]}))

        with self.assertRaises(ApiError) as ctx:
            api.orders.create([{"isbn": "978A", "cantidad": 3}])

        message = friendly_message(ctx.exception)
        self.assertIn("No hay stock suficiente", message)
        self.assertIn("978A: pediste 3, disponibles 1", message)


class PaymentsTests(unittest.TestCase):
    def test_create_attempt_never_sends_amount(self):
        api, transport = logged_in()
        transport.on("POST", "/payments", data({"pago_id": 9, "estado": "pending"}))

        api.payments.create(4, "bank_transfer", "TRX-1")
        api.payments.create(4, "cash")

        self.assertEqual(transport.calls[0].json, {"pedido_id": 4, "metodo_pago": "bank_transfer", "referencia": "TRX-1"})
        self.assertEqual(transport.calls[1].json, {"pedido_id": 4, "metodo_pago": "cash"})

    def test_admin_actions(self):
        api, transport = logged_in(role_id=2)
        for action in ("approve", "reject", "refund"):
            transport.on("POST", f"/payments/9/{action}", data({"payment": {}, "order": {}}))
        transport.on("GET", "/payments", ok({"success": True, "data": []}))

        api.payments.approve(9)
        api.payments.reject(9)
        api.payments.refund(9)
        api.payments.list_all(estado="pending")

        self.assertEqual(transport.paths()[:3], ["POST /payments/9/approve", "POST /payments/9/reject", "POST /payments/9/refund"])
        self.assertTrue(transport.calls[0].base.endswith(":5005"))
        self.assertEqual(transport.calls[3].query["estado"], "pending")

    def test_payment_conflicts_are_explained(self):
        for code, fragment in [
            ("ORDER_NOT_PAYABLE", "ya no se puede pagar"),
            ("PAYMENT_ALREADY_APPROVED", "ya fue aprobado"),
            ("PAYMENT_ALREADY_REFUNDED", "ya fue reembolsado"),
            ("REFUND_NOT_ALLOWED", "no se puede reembolsar"),
            ("ORDER_ALREADY_CANCELLED", "ya estaba cancelado"),
        ]:
            self.assertIn(fragment, friendly_message(ApiError(409, code, "x", "payments")))


if __name__ == "__main__":
    unittest.main()
