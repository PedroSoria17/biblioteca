"""
Payments :5005.

- MyPaymentsTab: the user's payments (only payments of their own orders).
- AllPaymentsTab (ADMIN): approve / reject pending payments, refund
  approved ones. The backend moves the order (paid / cancelled) and the
  stock in the same transaction; the client only reports the result.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.common import Table


PAYMENT_STATES = ("", "pending", "approved", "rejected", "refunded")
PAYMENT_STATE_TEXT = {
    "pending": "Payment pending — pendiente de aprobación",
    "approved": "Payment approved — aprobado",
    "rejected": "Payment rejected — rechazado",
    "refunded": "Payment refunded — reembolsado",
}

COLUMNS = [
    ("pago_id", "Pago", 60), ("pedido_id", "Pedido", 60), ("monto", "Monto", 80), ("metodo_pago", "Método", 110),
    ("estado_text", "Estado", 280), ("referencia", "Referencia", 220), ("fecha_creacion", "Registrado", 200),
]


def decorate_payments(payments: list[dict]) -> list[dict]:
    for payment in payments:
        payment["estado_text"] = PAYMENT_STATE_TEXT.get(payment["estado"], payment["estado"])
    return payments


def _tags(table: Table) -> None:
    table.tree.tag_configure("pending", foreground="#b07800")
    table.tree.tag_configure("approved", foreground="#2e7d32")
    table.tree.tag_configure("rejected", foreground="#c62828")
    table.tree.tag_configure("refunded", foreground="#5e35b1")


class MyPaymentsTab(ttk.Frame):
    title = "Mis pagos"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refrescar", command=self.refresh).pack(side="left")
        ttk.Label(bar, text="Los pagos se registran desde 'Mis pedidos' → 'Pagar pedido'.").pack(side="left", padx=10)
        self.table = Table(self, COLUMNS + [("fecha_pago", "Fecha de pago", 200)], height=18)
        self.table.pack(fill="both", expand=True, pady=8)
        _tags(self.table)

    def refresh(self) -> None:
        self.ctx.run(self.ctx.api.payments.mine,
                     lambda r: self.table.set_rows(decorate_payments(r["data"]), tag_for=lambda p: p["estado"]),
                     busy="Cargando mis pagos...")


class AllPaymentsTab(ttk.Frame):
    title = "Pagos (admin)"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="Estado").pack(side="left")
        self.estado_var = tk.StringVar(self, value="pending")
        combo = ttk.Combobox(bar, textvariable=self.estado_var, values=PAYMENT_STATES, state="readonly", width=11)
        combo.pack(side="left", padx=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(bar, text="Refrescar", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(bar, text="Reembolsar", command=lambda: self.act("refund")).pack(side="right")
        ttk.Button(bar, text="Rechazar", command=lambda: self.act("reject")).pack(side="right", padx=6)
        ttk.Button(bar, text="Aprobar", command=lambda: self.act("approve")).pack(side="right")

        self.table = Table(self, [("usuario_id", "Usuario", 60)] + COLUMNS, height=18)
        self.table.pack(fill="both", expand=True, pady=8)
        _tags(self.table)

    def refresh(self) -> None:
        estado = self.estado_var.get() or None
        self.ctx.run(lambda: self.ctx.api.payments.list_all(estado=estado),
                     lambda r: (self.table.set_rows(decorate_payments(r["data"]), tag_for=lambda p: p["estado"]),
                                self.ctx.status_var.set(f"{r['pagination']['total']} pago(s).")),
                     busy="Cargando pagos...")

    def act(self, action: str) -> None:
        payment = self.table.selected()
        if payment is None:
            self.ctx.info("Selecciona un pago", "Selecciona un pago de la lista.")
            return
        question = {
            "approve": "Aprobar el pago #{pago_id} ({monto})?\nEl pedido #{pedido_id} pasará a 'paid'.",
            "reject": "Rechazar el pago #{pago_id}?\nEl pedido #{pedido_id} seguirá 'pending'.",
            "refund": "Reembolsar el pago #{pago_id} ({monto})?\nEl pedido #{pedido_id} pasará a 'cancelled' y se devolverá el stock.",
        }[action].format(**payment)
        if not self.ctx.confirm("Confirmar", question):
            return
        call = getattr(self.ctx.api.payments, action)

        def done(result):
            payment_after, order = result["payment"], result["order"]
            message = (f"Pago #{payment_after['pago_id']}: {PAYMENT_STATE_TEXT[payment_after['estado']]}\n"
                       f"Pedido #{order['pedido_id']}: {order['estado']}")
            if result.get("restocked"):
                message += "\nStock devuelto: " + ", ".join(f"{r['isbn']} +{r['cantidad']}" for r in result["restocked"])
            self.ctx.info("Operación realizada", message)
            self.refresh()

        self.ctx.run(lambda: call(payment["pago_id"]), done, busy="Procesando pago...")
