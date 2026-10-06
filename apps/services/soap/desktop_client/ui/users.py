"""Users tab (ADMIN only): Users :5002. password_hash never exists here."""

from __future__ import annotations

from tkinter import ttk

from api.session import ROLE_ADMIN, ROLE_USER
from ui.common import FormDialog, Table, changed_fields


ROLE_OPTIONS = {"USER": ROLE_USER, "ADMIN": ROLE_ADMIN}


class UsersTab(ttk.Frame):
    title = "Usuarios"

    def __init__(self, parent, ctx) -> None:
        super().__init__(parent, padding=10)
        self.ctx = ctx

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        for text, command in (
            ("Refrescar", self.refresh), ("Nuevo usuario", self.create), ("Editar", self.edit),
            ("Activar / Desactivar", self.toggle_active), ("Cambiar contraseña", self.change_password),
            ("Eliminar", self.delete),
        ):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=(0, 6))

        self.table = Table(self, [
            ("usuario_id", "ID", 50), ("nombre_completo", "Nombre", 220), ("email", "Email", 230),
            ("role", "Rol", 70), ("activo_text", "Activo", 70), ("fecha_registro", "Registro", 200),
        ], height=18)
        self.table.pack(fill="both", expand=True, pady=8)
        self.table.tree.tag_configure("inactive", foreground="#888888")

    def refresh(self) -> None:
        self.ctx.run(self.ctx.api.users.list, lambda r: self._render(r["data"]), busy="Cargando usuarios...")

    def _render(self, users) -> None:
        for user in users:
            user["activo_text"] = "sí" if user["activo"] else "no"
        self.table.set_rows(users, tag_for=lambda u: None if u["activo"] else "inactive")
        self.ctx.status_var.set(f"{len(users)} usuario(s).")

    def _selected(self) -> dict | None:
        user = self.table.selected()
        if user is None:
            self.ctx.info("Selecciona un usuario", "Selecciona un usuario de la lista.")
        return user

    def _done(self, message: str):
        return lambda _r: (self.ctx.status_var.set(message), self.refresh())

    def create(self) -> None:
        values = FormDialog.ask(self, "Nuevo usuario", [
            {"key": "nombre_completo", "label": "Nombre completo"},
            {"key": "email", "label": "Email"},
            {"key": "password", "label": "Contraseña (mín. 8)", "kind": "password"},
            {"key": "role", "label": "Rol", "kind": "combo", "options": list(ROLE_OPTIONS), "initial": "USER"},
            {"key": "activo", "label": "Activo", "kind": "check", "initial": True},
        ])
        if not values:
            return
        body = {
            "nombre_completo": values["nombre_completo"], "email": values["email"], "password": values["password"],
            "role_id": ROLE_OPTIONS[values["role"]], "activo": values["activo"],
        }
        self.ctx.run(lambda: self.ctx.api.users.create(body), self._done("Usuario creado."))

    def edit(self) -> None:
        user = self._selected()
        if user is None:
            return
        values = FormDialog.ask(self, f"Editar usuario #{user['usuario_id']}", [
            {"key": "nombre_completo", "label": "Nombre completo", "initial": user["nombre_completo"]},
            {"key": "email", "label": "Email", "initial": user["email"]},
            {"key": "role", "label": "Rol", "kind": "combo", "options": list(ROLE_OPTIONS), "initial": user["role"]},
            {"key": "activo", "label": "Activo", "kind": "check", "initial": user["activo"]},
        ])
        if not values:
            return
        edited = {"nombre_completo": values["nombre_completo"], "email": values["email"],
                  "role_id": ROLE_OPTIONS[values["role"]], "activo": values["activo"]}
        changes = changed_fields(user, edited)
        if not changes:
            self.ctx.status_var.set("Sin cambios.")
            return
        self.ctx.run(lambda: self.ctx.api.users.update(user["usuario_id"], changes), self._done("Usuario actualizado."))

    def toggle_active(self) -> None:
        user = self._selected()
        if user is None:
            return
        target = not user["activo"]
        verb = "activar" if target else "desactivar"
        if self.ctx.confirm("Confirmar", f"¿Deseas {verb} a {user['email']}?"):
            self.ctx.run(lambda: self.ctx.api.users.update(user["usuario_id"], {"activo": target}),
                         self._done(f"Usuario {'activado' if target else 'desactivado'}."))

    def change_password(self) -> None:
        user = self._selected()
        if user is None:
            return
        values = FormDialog.ask(self, f"Contraseña de {user['email']}", [
            {"key": "password", "label": "Nueva contraseña", "kind": "password"},
            {"key": "confirm", "label": "Repetir contraseña", "kind": "password"},
        ])
        if not values:
            return
        if values["password"] != values["confirm"]:
            self.ctx.show_error(ValueError("Las contraseñas no coinciden."), "Contraseña")
            return
        password = values["password"]
        values.clear()  # do not keep the password around longer than needed
        self.ctx.run(lambda: self.ctx.api.users.change_password(user["usuario_id"], password),
                     self._done("Contraseña actualizada."))

    def delete(self) -> None:
        user = self._selected()
        if user is None:
            return
        if self.ctx.confirm("Eliminar usuario", f"¿Eliminar a {user['email']}?\n"
                            "Si tiene pedidos no se podrá eliminar (desactívalo)."):
            self.ctx.run(lambda: self.ctx.api.users.delete(user["usuario_id"]), self._done("Usuario eliminado."))
