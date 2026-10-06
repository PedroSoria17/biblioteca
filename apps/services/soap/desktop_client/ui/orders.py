"""
Orders :5004 (+ registering a payment attempt on Payments :5005).

- MyOrdersTab: local cart -> POST /orders {"items": [{"isbn", "cantidad"}]};
  own orders, their lines (historical price, subtotal) and "Pagar pedido".
- AllOrdersTab (ADMIN): every order with filters; pending -> cancelled and
  paid -> completed. pending -> paid is NOT offered: Payments does it when
  a payment is approved.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from api.services import PaymentsApi
from ui.common import FormDialog, Table


ORDER_STATES = ("", "pending", "paid", "completed", "cancelled")
ORDER_STATE_TEXT = {
    "pending": "pending — pendiente de pago",
    "paid": "paid — pagado",
    "completed": "completed — completado",
    "cancelled": "cancelled — cancelado",
}

ORDER_COLUMNS = [
    ("pedido_id", "Pedido", 70), ("estado_text", "Estado", 190), ("total", "Total", 90),
    ("items_count", "Líneas", 60), ("fecha_creacion", "Fecha", 220),
]
ITEM_COLUMNS = [
    ("isbn", "ISBN", 130), ("titulo", "Título", 260), ("cantidad", "Cantidad", 70),
    ("precio_unitario", "Precio histórico", 110), ("subtotal", "Subtotal", 90),
]


def decorate_orders(orders: list[dict]) -> list[dict]:
    for order in orders:
        order["estado_text"] = ORDER_STATE_TEXT.get(order["estado"], order["estado"])
    return orders


def ask_payment(parent, pedido: dict) -> dict | None:
    """The amount is NOT asked: Payments uses the real order total."""
    return FormDialog.ask(parent, f"Pagar pedido #{pedido['pedido_id']} (total {pedido['total']})", [
        {"key": "metodo_pago", "label": "Método de pago", "kind": "combo", "options": list(PaymentsApi.METHODS),
         "initial": "credit_card"},
        {"key": "referencia", "label": "Referencia (opcional)", "required": False},
    ], submit_text="Registrar pago")


class MyOrdersTab(ttk.Frame):
    title = "Mis pedidos"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx

        cart_frame = ttk.LabelFrame(self, text="Carrito (local, aún no enviado)", padding=6)
        cart_frame.pack(fill="x")
        self.cart_table = Table(cart_frame, [("isbn", "ISBN", 140), ("titulo", "Título", 360), ("cantidad", "Cantidad", 80)], height=4)
        self.cart_table.pack(fill="x")
        cart_bar = ttk.Frame(cart_frame)
        cart_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(cart_bar, text="Confirmar pedido", command=self.place_order).pack(side="left")
        ttk.Button(cart_bar, text="Quitar línea", command=self.remove_line).pack(side="left", padx=6)
        ttk.Button(cart_bar, text="Vaciar carrito", command=self.clear_cart).pack(side="left")

        orders_frame = ttk.LabelFrame(self, text="Mis pedidos", padding=6)
        orders_frame.pack(fill="both", expand=True, pady=(8, 0))
        bar = ttk.Frame(orders_frame)
        bar.pack(fill="x")
        ttk.Label(bar, text="Estado").pack(side="left")
        self.estado_var = tk.StringVar(self, value="")
        combo = ttk.Combobox(bar, textvariable=self.estado_var, values=ORDER_STATES, state="readonly", width=12)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(bar, text="Refrescar", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Pagar pedido", command=self.pay).pack(side="right")
        ttk.Button(bar, text="Ver pagos del pedido", command=self.show_payments).pack(side="right", padx=6)

        panes = ttk.Panedwindow(orders_frame, orient="vertical")
        panes.pack(fill="both", expand=True, pady=6)
        self.orders = Table(panes, ORDER_COLUMNS, height=7)
        self.orders.bind_select(self.load_items)
        panes.add(self.orders, weight=1)
        self.items = Table(panes, ITEM_COLUMNS, height=5)
        panes.add(self.items, weight=1)

        self.refresh_cart()

    # -- cart ---------------------------------------------------------------

    def refresh_cart(self) -> None:
        self.cart_table.set_rows([vars(line) for line in self.ctx.cart.lines])

    def remove_line(self) -> None:
        line = self.cart_table.selected()
        if line:
            self.ctx.cart.remove(line["isbn"])
            self.refresh_cart()

    def clear_cart(self) -> None:
        self.ctx.cart.clear()
        self.refresh_cart()

    def place_order(self) -> None:
        if self.ctx.cart.is_empty():
            self.ctx.info("Carrito vacío", "Agrega libros desde la pestaña Catálogo.")
            return
        items = self.ctx.cart.to_order_items()

        def done(order):
            self.ctx.cart.clear()
            self.refresh_cart()
            self.ctx.info("Pedido creado",
                          f"Pedido #{order['pedido_id']} creado.\nEstado: {order['estado']}\nTotal: {order['total']}\n\n"
                          "El stock ya fue reservado. Puedes registrar el pago con 'Pagar pedido'.")
            self.refresh()

        # INSUFFICIENT_STOCK / BOOK_NOT_FOUND are explained by friendly_message.
        self.ctx.run(lambda: self.ctx.api.orders.create(items), done, busy="Creando pedido...")

    # -- orders ---------------------------------------------------------------

    def refresh(self) -> None:
        estado = self.estado_var.get() or None
        self.refresh_cart()
        self.ctx.run(lambda: self.ctx.api.orders.mine(estado=estado),
                     lambda r: (self.orders.set_rows(decorate_orders(r["data"])), self.items.set_rows([])),
                     busy="Cargando mis pedidos...")

    def load_items(self) -> None:
        order = self.orders.selected()
        if order:
            self.ctx.run(lambda: self.ctx.api.orders.items(order["pedido_id"]), lambda d: self.items.set_rows(d["items"]))

    def _selected(self) -> dict | None:
        order = self.orders.selected()
        if order is None:
            self.ctx.info("Selecciona un pedido", "Selecciona un pedido de la lista.")
        return order

    def pay(self) -> None:
        order = self._selected()
        if order is None:
            return
        if order["estado"] != "pending":
            self.ctx.info("No se puede pagar", f"El pedido #{order['pedido_id']} está '{order['estado']}'.")
            return
        values = ask_payment(self, order)
        if not values:
            return
        self.ctx.run(
            lambda: self.ctx.api.payments.create(order["pedido_id"], values["metodo_pago"], values["referencia"]),
            lambda p: self.ctx.info("Pago registrado",
                                    f"Pago #{p['pago_id']} por {p['monto']} ({p['metodo_pago']}).\n\n"
                                    "Pago pendiente de aprobación."),
            busy="Registrando pago...",
        )

    def show_payments(self) -> None:
        order = self._selected()
        if order is None:
            return

        def show(data):
            lines = [f"#{p['pago_id']}  {p['estado']:<9} {p['monto']:>10}  {p['metodo_pago']}  {p['referencia']}"
                     for p in data["payments"]] or ["Sin pagos registrados."]
            self.ctx.info(f"Pagos del pedido #{order['pedido_id']} ({data['order']['estado']})", "\n".join(lines))

        self.ctx.run(lambda: self.ctx.api.payments.for_order(order["pedido_id"]), show)


class AllOrdersTab(ttk.Frame):
    title = "Pedidos (admin)"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx

        filters = ttk.Frame(self)
        filters.pack(fill="x")
        self.vars = {name: tk.StringVar(self) for name in ("estado", "usuario_id", "desde", "hasta")}
        ttk.Label(filters, text="Estado").pack(side="left")
        ttk.Combobox(filters, textvariable=self.vars["estado"], values=ORDER_STATES, state="readonly", width=11).pack(side="left", padx=4)
        for name, label, width in (("usuario_id", "Usuario ID", 7), ("desde", "Desde (AAAA-MM-DD)", 11), ("hasta", "Hasta", 11)):
            ttk.Label(filters, text=label).pack(side="left", padx=(8, 0))
            ttk.Entry(filters, textvariable=self.vars[name], width=width).pack(side="left", padx=4)
        ttk.Button(filters, text="Filtrar", command=self.refresh).pack(side="left", padx=6)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Cancelar pedido (pending → cancelled)", command=lambda: self.set_status("cancelled")).pack(side="left")
        ttk.Button(actions, text="Marcar completado (paid → completed)", command=lambda: self.set_status("completed")).pack(side="left", padx=6)
        ttk.Label(actions, text="pending → paid lo hace Payments al aprobar un pago.").pack(side="left", padx=8)

        panes = ttk.Panedwindow(self, orient="vertical")
        panes.pack(fill="both", expand=True, pady=6)
        self.orders = Table(panes, [("pedido_id", "Pedido", 70), ("usuario_id", "Usuario", 70)] + ORDER_COLUMNS[1:], height=10)
        self.orders.bind_select(self.load_items)
        panes.add(self.orders, weight=2)
        self.items = Table(panes, ITEM_COLUMNS, height=5)
        panes.add(self.items, weight=1)

    def refresh(self) -> None:
        f = {k: (v.get().strip() or None) for k, v in self.vars.items()}
        try:
            usuario_id = int(f["usuario_id"]) if f["usuario_id"] else None
        except ValueError:
            self.ctx.show_error(ValueError("Usuario ID debe ser un número."), "Filtro inválido")
            return
        self.ctx.run(lambda: self.ctx.api.orders.list_all(estado=f["estado"], usuario_id=usuario_id, desde=f["desde"], hasta=f["hasta"]),
                     lambda r: (self.orders.set_rows(decorate_orders(r["data"])), self.items.set_rows([]),
                                self.ctx.status_var.set(f"{r['pagination']['total']} pedido(s).")),
                     busy="Cargando pedidos...")

    def load_items(self) -> None:
        order = self.orders.selected()
        if order:
            self.ctx.run(lambda: self.ctx.api.orders.items(order["pedido_id"]), lambda d: self.items.set_rows(d["items"]))

    def set_status(self, estado: str) -> None:
        order = self.orders.selected()
        if order is None:
            self.ctx.info("Selecciona un pedido", "Selecciona un pedido de la lista.")
            return
        extra = "\nEl stock reservado se devolverá." if estado == "cancelled" else ""
        if not self.ctx.confirm("Cambiar estado", f"Pedido #{order['pedido_id']}: {order['estado']} → {estado}?{extra}"):
            return
        self.ctx.run(lambda: self.ctx.api.orders.set_status(order["pedido_id"], estado),
                     lambda o: (self.ctx.status_var.set(f"Pedido #{o['pedido_id']} → {o['estado']}."), self.refresh()))
