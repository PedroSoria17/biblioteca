"""
Tkinter smoke tests with the fake transport (no services, no network).
Message boxes and form dialogs are patched (they would block); the Tk event
loop is pumped manually. Skipped if no display/Tk is available.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from unittest import mock

from api import LibraryApi
from fakes import CONFIG, FakeTransport, err, ok


BOOKS = [
    {"isbn": "9780000000001", "titulo": "Libro A", "anio_publicacion": 2001, "precio": "10.50", "stock": 7,
     "categoria": "Infantil", "formato": "Digital"},
    {"isbn": "9780000000002", "titulo": "Libro B", "anio_publicacion": 2002, "precio": "20.00", "stock": 0,
     "categoria": "Comic", "formato": "Tapa dura"},
]


def tk_available() -> bool:
    try:
        root = tk.Tk()
        root.destroy()
        return True
    except tk.TclError:
        return False


def button_texts(widget) -> list[str]:
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button):
            texts.append(child.cget("text"))
        texts.extend(button_texts(child))
    return texts


def login_payload(role_id):
    return {"success": True, "user": {"id": 7 if role_id == 1 else 1, "email": "u@example.com", "role_id": role_id},
            "access_token": "access-1", "refresh_token": "refresh-1"}


@unittest.skipUnless(tk_available(), "Tk display not available")
class UiTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.transport.on("GET", "/health", ok({"status": "healthy", "database": "connected", "redis": "connected"}))
        self.transport.on("GET", "/books", ok({"books": [dict(b) for b in BOOKS]}))
        self.transport.on("GET", "/authors", ok({"success": True, "data": [], "pagination": {"total": 0}}))
        self.transport.on("GET", "/orders/me", ok({"success": True, "data": [], "pagination": {"total": 0}}))
        self.transport.on("GET", "/payments/me", ok({"success": True, "data": [], "pagination": {"total": 0}}))
        self.transport.on("POST", "/logout", ok({"success": True}))
        self.messages = []
        patches = [
            mock.patch("tkinter.messagebox.showinfo", side_effect=lambda t, m, **k: self.messages.append(("info", t, m))),
            mock.patch("tkinter.messagebox.showerror", side_effect=lambda t, m, **k: self.messages.append(("error", t, m))),
            mock.patch("tkinter.messagebox.showwarning", side_effect=lambda t, m, **k: self.messages.append(("warning", t, m))),
            mock.patch("tkinter.messagebox.askyesno", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        from ui.app import MainApp

        self.api = LibraryApi(CONFIG, transport=self.transport)
        self.app = MainApp(CONFIG, api=self.api)
        self.app.withdraw()
        self.addCleanup(self._close)

    def _close(self):
        try:
            self.app.close()
        except tk.TclError:
            pass

    def pump(self, until, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if until():
                return
            time.sleep(0.01)
        self.fail("condition not reached while pumping the Tk loop")

    def login(self, role_id):
        from ui.login import LoginFrame

        self.transport.on("POST", "/login", ok(login_payload(role_id)))
        frame = self.app.current
        self.assertIsInstance(frame, LoginFrame)
        frame.email_var.set("u@example.com")
        frame.password_var.set("Password123")
        frame.login()
        self.assertEqual(frame.password_var.get(), "")  # password not kept in the widget
        self.pump(lambda: hasattr(self.app.current, "notebook"))
        return self.app.current

    def tab_titles(self, dashboard):
        return [dashboard.notebook.tab(t, "text") for t in dashboard.notebook.tabs()]

    # ------------------------------------------------------------------

    def test_user_dashboard_has_no_admin_tabs_or_buttons(self):
        dashboard = self.login(role_id=1)

        self.assertEqual(self.tab_titles(dashboard), ["Catálogo", "Autores", "Mis pedidos", "Mis pagos", "Clasificador SOAP"])
        for key, admin_button in (("catalog", "Nuevo libro"), ("authors", "Asociar libro")):
            texts = button_texts(dashboard.tabs[key])
            self.assertNotIn(admin_button, texts)
        self.assertIn("Agregar al carrito", button_texts(dashboard.tabs["catalog"]))

    def test_admin_dashboard_has_admin_tabs(self):
        dashboard = self.login(role_id=2)

        self.assertEqual(self.tab_titles(dashboard), [
            "Catálogo", "Autores", "Mis pedidos", "Mis pagos", "Usuarios", "Pedidos (admin)", "Pagos (admin)", "Clasificador SOAP",
        ])
        for key, admin_button in (("catalog", "Nuevo libro"), ("authors", "Asociar libro"), ("all_payments", "Reembolsar")):
            self.assertIn(admin_button, button_texts(dashboard.tabs[key]))

    def test_catalog_loads_with_stock_lights(self):
        dashboard = self.login(role_id=1)
        catalog = dashboard.tabs["catalog"]
        self.pump(lambda: len(catalog.table.rows()) == 2)

        rows = {r["isbn"]: r for r in catalog.table.rows()}
        self.assertEqual(rows["9780000000001"]["disponibilidad"], "Disponible")
        self.assertEqual(rows["9780000000002"]["disponibilidad"], "Agotado")

    def test_purchase_and_payment_flow(self):
        created = {"pedido_id": 11, "estado": "pending", "total": "21.00", "items": []}
        self.transport.on("POST", "/orders", ok({"success": True, "data": created}, 201))
        self.transport.on("GET", "/orders/11/items", ok({"success": True, "data": {"order": created, "items": []}}))
        self.transport.on("POST", "/payments", ok({"success": True, "data": {
            "pago_id": 5, "pedido_id": 11, "monto": "21.00", "metodo_pago": "cash", "estado": "pending"}}, 201))
        dashboard = self.login(role_id=1)
        catalog = dashboard.tabs["catalog"]
        self.pump(lambda: len(catalog.table.rows()) == 2)

        # Add 2 units of book A to the local cart.
        item = catalog.table.tree.get_children()[0]
        catalog.table.tree.selection_set(item)
        catalog.qty_var.set("2")
        catalog.add_to_cart()
        self.assertEqual(self.app.ctx.cart.to_order_items(), [{"isbn": "9780000000001", "cantidad": 2}])

        orders = dashboard.tabs["my_orders"]
        orders.place_order()
        self.pump(lambda: any(m[1] == "Pedido creado" for m in self.messages))
        post = next(c for c in self.transport.calls if c.method == "POST" and c.path == "/orders")
        self.assertEqual(post.json, {"items": [{"isbn": "9780000000001", "cantidad": 2}]})  # no price/total/user
        self.assertTrue(self.app.ctx.cart.is_empty())

        # Pay the pending order (amount is never asked).
        orders.orders.set_rows([{**created, "items_count": 1, "fecha_creacion": "2026-10-05", "estado_text": "pending"}])
        orders.orders.tree.selection_set(orders.orders.tree.get_children()[0])
        with mock.patch("ui.orders.FormDialog.ask", return_value={"metodo_pago": "cash", "referencia": None}):
            orders.pay()
        self.pump(lambda: any(m[1] == "Pago registrado" for m in self.messages))
        pay = next(c for c in self.transport.calls if c.path == "/payments" and c.method == "POST")
        self.assertEqual(pay.json, {"pedido_id": 11, "metodo_pago": "cash"})
        message = next(m for _k, t, m in self.messages if t == "Pago registrado")
        self.assertIn("Pago pendiente de aprobación", message)
        self.assertFalse([m for m in self.messages if m[0] == "error"])

    def test_insufficient_stock_is_shown_friendly(self):
        self.transport.on("POST", "/orders", err(409, "INSUFFICIENT_STOCK", "x",
                                                  {"items": [{"isbn": "9780000000002", "requested": 1, "available": 0}]}))
        dashboard = self.login(role_id=1)
        self.app.ctx.cart.add("9780000000002", "Libro B", 1)

        dashboard.tabs["my_orders"].place_order()
        self.pump(lambda: any(m[0] == "error" for m in self.messages))

        title, message = [(t, m) for kind, t, m in self.messages if kind == "error"][0]
        self.assertIn("No hay stock suficiente", message)
        self.assertFalse(self.app.ctx.cart.is_empty())  # the cart is kept to fix it

    def test_admin_approves_payment(self):
        payment = {"pago_id": 5, "pedido_id": 11, "usuario_id": 7, "monto": "21.00", "metodo_pago": "cash",
                   "estado": "pending", "referencia": "PAY-1", "fecha_creacion": "2026-10-05"}
        self.transport.on("GET", "/payments", ok({"success": True, "data": [payment], "pagination": {"total": 1}}))
        self.transport.on("POST", "/payments/5/approve", ok({"success": True, "data": {
            "payment": {**payment, "estado": "approved"}, "order": {"pedido_id": 11, "estado": "paid", "total": "21.00"}}}))
        dashboard = self.login(role_id=2)
        tab = dashboard.tabs["all_payments"]
        tab.refresh()
        self.pump(lambda: len(tab.table.rows()) == 1)

        tab.table.tree.selection_set(tab.table.tree.get_children()[0])
        tab.act("approve")
        self.pump(lambda: any(m[1] == "Operación realizada" for m in self.messages))

        self.assertIn("Pedido #11: paid", self.messages[-1][2])

    def test_logout_returns_to_login_even_if_login_service_is_down(self):
        from ui.login import LoginFrame

        self.login(role_id=1)
        self.transport.down_hosts.add("http://127.0.0.1:5001")

        self.app.logout()
        self.pump(lambda: isinstance(self.app.current, LoginFrame))
        self.assertFalse(self.api.session.is_authenticated)

    def test_rejected_refresh_returns_to_login(self):
        from ui.login import LoginFrame

        dashboard = self.login(role_id=1)
        self.transport.on("GET", "/payments/me", err(401, "TOKEN_EXPIRED", "expired"))
        self.transport.on("POST", "/refresh", err(401, "TOKEN_REVOKED", "revoked"))

        dashboard.tabs["my_payments"].refresh()
        self.pump(lambda: isinstance(self.app.current, LoginFrame))
        self.assertFalse(self.api.session.is_authenticated)
        self.assertTrue(any(kind == "warning" and "sesión expiró" in m for kind, _t, m in self.messages))

    def test_service_lights_show_down_service(self):
        self.transport.down_hosts.add("http://127.0.0.1:5005")
        bar = self.app.status_bar
        self.pump(lambda: not bar._checking and "caído" in bar.lights["payments"][1].cget("text"))
        self.assertEqual(bar.lights["books"][1].cget("text"), "Books")

    def test_slow_service_does_not_freeze_the_ui(self):
        release = threading.Event()

        def slow_books(_call):
            release.wait(5)
            return ok({"books": []})

        self.transport.on("GET", "/books", slow_books)
        dashboard = self.login(role_id=1)
        # The request is in flight in a worker thread; the Tk loop keeps running.
        started = time.monotonic()
        for _ in range(20):
            self.app.update()
        self.assertLess(time.monotonic() - started, 1.0)
        release.set()
        self.pump(lambda: self.app.ctx.status_var.get().endswith("catálogo."))
        self.assertIsNotNone(dashboard)


@unittest.skipUnless(tk_available(), "Tk display not available")
class DispatcherTests(unittest.TestCase):
    def test_worker_results_run_in_the_main_thread(self):
        from ui.common import UiDispatcher

        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        dispatcher = UiDispatcher(root)
        seen = []
        threading.Thread(target=lambda: dispatcher.call_soon(lambda: seen.append(threading.current_thread()))).start()

        deadline = time.monotonic() + 3
        while not seen and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        self.assertEqual(seen, [threading.main_thread()])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(tk_available(), "Tk display not available")
class SoapClassifierTests(unittest.TestCase):
    def test_standalone_classifier_still_works_and_reports_connection_errors(self):
        """
        The original SOAP window keeps working alone. Its error path used to
        capture `exc` in a lambda after the except block (NameError, the
        error dialog never appeared); now the error reaches the user.
        """
        from desktop_app import LibraryClassifierApp, SoapClassifierFrame

        errors = []
        with mock.patch("desktop_app.messagebox.showerror", side_effect=lambda t, m: errors.append(m)):
            app = LibraryClassifierApp()
            app.withdraw()
            try:
                frame = next(w for w in app.winfo_children() if isinstance(w, SoapClassifierFrame))
                self.assertEqual(frame.endpoint_var.get(), "http://127.0.0.1:5000/soap")  # from client_config
                frame.endpoint_var.set("http://127.0.0.1:9/soap")  # nothing listens there
                frame.refresh_progress()
                deadline = time.monotonic() + 15
                while not errors and time.monotonic() < deadline:
                    app.update()
                    time.sleep(0.01)
            finally:
                frame.dispatcher.close()
                app.destroy()

        self.assertEqual(len(errors), 1)
        self.assertIn("No fue posible conectar", errors[0])
