"""Authors tab: Authors :5003. Everyone reads; ADMIN edits and links books."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from permissions import can
from ui.common import FormDialog, Table, changed_fields


class AuthorsTab(ttk.Frame):
    title = "Autores"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx
        role = ctx.role_id

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        self.q_var = tk.StringVar(self)
        ttk.Label(bar, text="Buscar").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.q_var, width=28)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _e: self.refresh())
        ttk.Button(bar, text="Buscar", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Refrescar", command=lambda: (self.q_var.set(""), self.refresh())).pack(side="left", padx=6)

        if can(role, "authors.create"):
            admin = ttk.Frame(bar)
            admin.pack(side="right")
            ttk.Button(admin, text="Nuevo autor", command=self.create).pack(side="left")
            ttk.Button(admin, text="Editar", command=self.edit).pack(side="left", padx=4)
            ttk.Button(admin, text="Eliminar", command=self.delete).pack(side="left")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, pady=8)

        left = ttk.LabelFrame(panes, text="Autores", padding=6)
        self.authors = Table(left, [
            ("autor_id", "ID", 50), ("nombre", "Nombre", 150), ("apellido", "Apellido", 150),
            ("pais", "País", 110), ("books_count", "Libros", 60),
        ], height=16)
        self.authors.pack(fill="both", expand=True)
        self.authors.bind_select(self.load_books)
        panes.add(left, weight=3)

        right = ttk.LabelFrame(panes, text="Libros del autor", padding=6)
        self.books = Table(right, [
            ("isbn", "ISBN", 130), ("titulo", "Título", 230), ("anio_publicacion", "Año", 60), ("orden", "Orden", 60),
        ], height=16)
        self.books.pack(fill="both", expand=True)
        if can(role, "authors.link"):
            links = ttk.Frame(right)
            links.pack(fill="x", pady=(6, 0))
            ttk.Button(links, text="Asociar libro", command=self.link).pack(side="left")
            ttk.Button(links, text="Quitar libro seleccionado", command=self.unlink).pack(side="left", padx=6)
        panes.add(right, weight=2)

    def refresh(self) -> None:
        q = self.q_var.get().strip() or None
        self.ctx.run(lambda: self.ctx.api.authors.list(q=q), lambda r: self._render(r["data"]), busy="Cargando autores...")

    def _render(self, authors) -> None:
        self.authors.set_rows(authors)
        self.books.set_rows([])
        self.ctx.status_var.set(f"{len(authors)} autor(es).")

    def _selected(self) -> dict | None:
        author = self.authors.selected()
        if author is None:
            self.ctx.info("Selecciona un autor", "Selecciona un autor de la lista.")
        return author

    def load_books(self) -> None:
        author = self.authors.selected()
        if author is None:
            return
        self.ctx.run(lambda: self.ctx.api.authors.books(author["autor_id"]), lambda d: self.books.set_rows(d["books"]))

    # -- ADMIN ------------------------------------------------------------

    def _fields(self, author=None):
        author = author or {}
        return [
            {"key": "nombre", "label": "Nombre", "initial": author.get("nombre")},
            {"key": "apellido", "label": "Apellido", "initial": author.get("apellido")},
            {"key": "pais", "label": "País (opcional)", "initial": author.get("pais"), "required": False},
        ]

    def create(self) -> None:
        values = FormDialog.ask(self, "Nuevo autor", self._fields())
        if values:
            self.ctx.run(lambda: self.ctx.api.authors.create(values),
                         lambda a: (self.ctx.status_var.set(f"Autor #{a['autor_id']} creado."), self.refresh()))

    def edit(self) -> None:
        author = self._selected()
        if author is None:
            return
        values = FormDialog.ask(self, f"Editar autor #{author['autor_id']}", self._fields(author))
        if not values:
            return
        changes = changed_fields(author, values)
        if not changes:
            self.ctx.status_var.set("Sin cambios.")
            return
        self.ctx.run(lambda: self.ctx.api.authors.update(author["autor_id"], changes),
                     lambda _a: (self.ctx.status_var.set("Autor actualizado."), self.refresh()))

    def delete(self) -> None:
        author = self._selected()
        if author is None:
            return
        if not self.ctx.confirm("Eliminar autor", f"¿Eliminar a {author['nombre']} {author['apellido']}?\n"
                                "Los libros nunca se eliminan."):
            return
        # 409 AUTHOR_HAS_BOOKS is explained by api.errors.friendly_message.
        self.ctx.run(lambda: self.ctx.api.authors.delete(author["autor_id"]),
                     lambda _r: (self.ctx.status_var.set("Autor eliminado."), self.refresh()))

    def link(self) -> None:
        author = self._selected()
        if author is None:
            return
        values = FormDialog.ask(self, f"Asociar libro a {author['apellido']}", [
            {"key": "isbn", "label": "ISBN del libro"},
            {"key": "orden", "label": "Orden (opcional)", "kind": "int", "required": False},
        ], submit_text="Asociar")
        if values:
            self.ctx.run(lambda: self.ctx.api.authors.link_book(author["autor_id"], values["isbn"], values["orden"]),
                         lambda _r: (self.ctx.status_var.set("Libro asociado."), self.refresh_selected(author)))

    def unlink(self) -> None:
        author = self.authors.selected()
        book = self.books.selected()
        if author is None or book is None:
            self.ctx.info("Selecciona", "Selecciona un autor y uno de sus libros.")
            return
        if not self.ctx.confirm("Quitar relación", f"¿Quitar {book['titulo']} de {author['apellido']}?\n"
                                "No se borra ni el autor ni el libro."):
            return
        self.ctx.run(lambda: self.ctx.api.authors.unlink_book(author["autor_id"], book["isbn"]),
                     lambda _r: (self.ctx.status_var.set("Relación eliminada."), self.refresh_selected(author)))

    def refresh_selected(self, author) -> None:
        self.ctx.run(lambda: self.ctx.api.authors.books(author["autor_id"]), lambda d: self.books.set_rows(d["books"]))
