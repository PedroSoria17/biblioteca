"""Catalog tab: Books :5000 (REST JSON). Everyone reads; ADMIN edits."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from cart import parse_quantity
from permissions import can
from ui.common import FormDialog, Table, changed_fields


LOW_STOCK = 5


def availability(stock: int) -> str:
    """Stock "traffic light" shown in the catalog."""
    if stock <= 0:
        return "Agotado"
    if stock < LOW_STOCK:
        return "Pocas unidades"
    return "Disponible"


class CatalogTab(ttk.Frame):
    title = "Catálogo"

    def __init__(self, parent, ctx, on_cart_changed) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx
        self.on_cart_changed = on_cart_changed
        role = ctx.role_id

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.q_var = tk.StringVar(self)
        ttk.Label(bar, text="Buscar (título o ISBN)").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.q_var, width=30)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _e: self.refresh())
        ttk.Button(bar, text="Buscar", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Refrescar", command=self._clear_and_refresh).pack(side="left", padx=6)

        if can(role, "books.create"):
            admin = ttk.Frame(bar)
            admin.pack(side="right")
            ttk.Button(admin, text="Nuevo libro", command=self.create).pack(side="left")
            ttk.Button(admin, text="Editar", command=self.edit).pack(side="left", padx=4)
            ttk.Button(admin, text="Eliminar", command=self.delete).pack(side="left")

        self.table = Table(self, [
            ("isbn", "ISBN", 130), ("titulo", "Título", 300), ("anio_publicacion", "Año", 60),
            ("precio", "Precio", 80), ("stock", "Stock", 60), ("disponibilidad", "Disponibilidad", 120),
            ("categoria", "Categoría", 120), ("formato", "Formato", 110),
        ], height=16)
        self.table.pack(fill="both", expand=True, pady=8)
        self.table.tree.tag_configure("agotado", foreground="#c62828")
        self.table.tree.tag_configure("bajo", foreground="#b07800")
        self.table.tree.tag_configure("ok", foreground="#2e7d32")

        cart_bar = ttk.Frame(self)
        cart_bar.pack(fill="x")
        ttk.Label(cart_bar, text="Cantidad").pack(side="left")
        self.qty_var = tk.StringVar(self, value="1")
        ttk.Spinbox(cart_bar, from_=1, to=999, textvariable=self.qty_var, width=6).pack(side="left", padx=6)
        ttk.Button(cart_bar, text="Agregar al carrito", command=self.add_to_cart).pack(side="left")
        ttk.Label(cart_bar, text="El precio y el total los calcula el servidor al crear el pedido.").pack(side="left", padx=12)

    # ------------------------------------------------------------------

    def refresh(self) -> None:
        q = self.q_var.get().strip() or None
        self.ctx.run(lambda: self.ctx.api.books.list(q), self._render, busy="Cargando catálogo...")

    def _clear_and_refresh(self) -> None:
        self.q_var.set("")
        self.refresh()

    def _render(self, books) -> None:
        for book in books:
            book["disponibilidad"] = availability(int(book.get("stock") or 0))

        def tag(book):
            stock = int(book.get("stock") or 0)
            return "agotado" if stock <= 0 else ("bajo" if stock < LOW_STOCK else "ok")

        self.table.set_rows(books, tag_for=tag)
        self.ctx.status_var.set(f"{len(books)} libro(s) en el catálogo.")

    def _selected(self) -> dict | None:
        book = self.table.selected()
        if book is None:
            self.ctx.info("Selecciona un libro", "Selecciona un libro de la lista.")
        return book

    def add_to_cart(self) -> None:
        book = self._selected()
        if book is None:
            return
        try:
            quantity = parse_quantity(self.qty_var.get())
            line = self.ctx.cart.add(book["isbn"], book["titulo"], quantity)
        except ValueError as exc:
            self.ctx.show_error(exc, "Cantidad inválida")
            return
        self.on_cart_changed()
        self.ctx.status_var.set(f"Carrito: {line.titulo} × {line.cantidad}. Confírmalo en 'Mis pedidos'.")

    # -- ADMIN ------------------------------------------------------------

    def create(self) -> None:
        values = FormDialog.ask(self, "Nuevo libro", [
            {"key": "isbn", "label": "ISBN"},
            {"key": "titulo", "label": "Título"},
            {"key": "anio_publicacion", "label": "Año de publicación", "kind": "int"},
            {"key": "precio", "label": "Precio"},
            {"key": "stock", "label": "Stock", "kind": "int", "initial": 0},
            {"key": "formato_id", "label": "ID de formato", "kind": "int"},
            {"key": "categoria_id", "label": "ID de categoría", "kind": "int"},
        ])
        if values:
            self.ctx.run(lambda: self.ctx.api.books.create(values),
                         lambda book: (self.ctx.info("Libro creado", f"{book['isbn']} — {book['titulo']}"), self.refresh()))

    def edit(self) -> None:
        book = self._selected()
        if book is None:
            return
        original = {k: book[k] for k in ("titulo", "anio_publicacion", "precio", "stock")}
        values = FormDialog.ask(self, f"Editar {book['isbn']}", [
            {"key": "titulo", "label": "Título", "initial": book["titulo"]},
            {"key": "anio_publicacion", "label": "Año de publicación", "kind": "int", "initial": book["anio_publicacion"]},
            {"key": "precio", "label": "Precio", "initial": book["precio"]},
            {"key": "stock", "label": "Stock", "kind": "int", "initial": book["stock"]},
            {"key": "formato_id", "label": "ID de formato (vacío = sin cambio)", "kind": "int", "required": False},
            {"key": "categoria_id", "label": "ID de categoría (vacío = sin cambio)", "kind": "int", "required": False},
        ])
        if not values:
            return
        changes = changed_fields(original, {k: values[k] for k in original})
        for key in ("formato_id", "categoria_id"):
            if values[key] is not None:
                changes[key] = values[key]
        if not changes:
            self.ctx.status_var.set("Sin cambios.")
            return
        self.ctx.run(lambda: self.ctx.api.books.update(book["isbn"], changes),
                     lambda _b: (self.ctx.status_var.set("Libro actualizado."), self.refresh()))

    def delete(self) -> None:
        book = self._selected()
        if book is None or not self.ctx.confirm("Eliminar libro", f"¿Eliminar {book['isbn']} — {book['titulo']}?"):
            return
        self.ctx.run(lambda: self.ctx.api.books.delete(book["isbn"]),
                     lambda _r: (self.ctx.status_var.set("Libro eliminado."), self.refresh()))
