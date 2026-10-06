"""
Main window: service traffic lights + Login screen or role-based Dashboard.

Tabs are built from permissions.tabs_for(role_id): a USER never gets the
administrative tabs or buttons (and the backend would answer 403 anyway).
Each tab reloads its data when it becomes visible, so the catalog shows
the stock taken by an order or given back by a cancellation/refund.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from api import LibraryApi
from cart import Cart
from desktop_app import SoapClassifierFrame
from permissions import tabs_for
from ui.authors import AuthorsTab
from ui.books import CatalogTab
from ui.common import AppContext, UiDispatcher
from ui.login import LoginFrame
from ui.orders import AllOrdersTab, MyOrdersTab
from ui.payments import AllPaymentsTab, MyPaymentsTab
from ui.service_status import ServiceStatusBar
from ui.users import UsersTab


class Dashboard(ttk.Frame):
    def __init__(self, parent, ctx, config, on_logout) -> None:
        super().__init__(parent)
        self.ctx = ctx
        user = ctx.api.session.user

        header = ttk.Frame(self, padding=(10, 6))
        header.pack(fill="x")
        ttk.Label(header, text="Library", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Cerrar sesión", command=on_logout).pack(side="right")
        ttk.Label(header, text=f"{user.email}  ·  {user.role_name}", font=("Segoe UI", 10)).pack(side="right", padx=12)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.tabs: dict[str, ttk.Frame] = {}

        builders = {
            "catalog": lambda: CatalogTab(self.notebook, ctx, on_cart_changed=self._cart_changed),
            "authors": lambda: AuthorsTab(self.notebook, ctx),
            "my_orders": lambda: MyOrdersTab(self.notebook, ctx),
            "my_payments": lambda: MyPaymentsTab(self.notebook, ctx),
            "users": lambda: UsersTab(self.notebook, ctx),
            "all_orders": lambda: AllOrdersTab(self.notebook, ctx),
            "all_payments": lambda: AllPaymentsTab(self.notebook, ctx),
            "classifier": lambda: SoapClassifierFrame(self.notebook, endpoint=config.soap_endpoint, dispatcher=ctx.dispatcher),
        }
        titles = {"classifier": "Clasificador SOAP"}
        for key in tabs_for(ctx.role_id):
            tab = builders[key]()
            self.tabs[key] = tab
            self.notebook.add(tab, text=titles.get(key, getattr(tab, "title", key)))

        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)

    def _current(self):
        return self.notebook.nametowidget(self.notebook.select())

    def _tab_changed(self, _event=None) -> None:
        tab = self._current()
        if hasattr(tab, "refresh"):
            tab.refresh()

    def _cart_changed(self) -> None:
        orders = self.tabs.get("my_orders")
        if orders is not None:
            orders.refresh_cart()


class MainApp(tk.Tk):
    def __init__(self, config, api: LibraryApi | None = None) -> None:
        super().__init__()
        self.title("Library — Desktop client (microservices)")
        self.geometry("1280x800")
        self.minsize(1080, 680)

        self.config_obj = config
        self.dispatcher = UiDispatcher(self)
        self.api = api or LibraryApi(config)
        # Called from a worker thread when a refresh is rejected: hop to Tk.
        self.api.client.on_session_expired = lambda: self.dispatcher.call_soon(self.session_expired)
        self.ctx = AppContext(self, self.api, self.dispatcher, Cart(), on_session_expired=self.session_expired)

        self.status_bar = ServiceStatusBar(self, self.api, self.dispatcher, config.health_refresh_seconds)
        self.status_bar.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Separator(self).pack(fill="x", pady=(4, 0))

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.ctx.status_var, relief="sunken", anchor="w", padding=(8, 4)).pack(fill="x")

        self.current: ttk.Frame | None = None
        self.show_login()
        self.status_bar.start()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _swap(self, frame: ttk.Frame) -> None:
        if self.current is not None:
            self.current.destroy()
        self.current = frame
        frame.pack(fill="both", expand=True)

    def show_login(self) -> None:
        self._swap(LoginFrame(self.body, self.ctx, on_logged_in=self.show_dashboard))

    def show_dashboard(self, _user=None) -> None:
        self.ctx.cart.clear()
        dashboard = Dashboard(self.body, self.ctx, self.config_obj, on_logout=self.logout)
        self._swap(dashboard)
        dashboard._tab_changed()

    def logout(self) -> None:
        # Remote revocation in background; the local session is cleared in any case.
        self.ctx.run(self.api.auth.logout, lambda _r: self._after_logout(), busy="Cerrando sesión...",
                     on_error=lambda _e: self._after_logout())

    def _after_logout(self) -> None:
        self.api.session.clear()
        self.ctx.cart.clear()
        self.ctx.status_var.set("Sesión cerrada.")
        self.show_login()

    def session_expired(self) -> None:
        if isinstance(self.current, LoginFrame):
            return
        self.api.session.clear()
        self.ctx.cart.clear()
        self.ctx.status_var.set("Tu sesión expiró. Inicia sesión nuevamente.")
        self.show_login()

    def close(self) -> None:
        self.dispatcher.close()
        self.destroy()
