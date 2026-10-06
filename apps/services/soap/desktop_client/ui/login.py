"""Login screen: POST :5001/login. The password is never kept after the call."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LoginFrame(ttk.Frame):
    def __init__(self, parent, ctx, on_logged_in) -> None:
        super().__init__(parent, padding=40)
        self.ctx = ctx
        self.on_logged_in = on_logged_in
        self.email_var = tk.StringVar(self)
        self.password_var = tk.StringVar(self)

        box = ttk.LabelFrame(self, text="Iniciar sesión", padding=20)
        box.place(relx=0.5, rely=0.4, anchor="center")
        ttk.Label(box, text="Library — cliente de escritorio", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 14))
        ttk.Label(box, text="Email").grid(row=1, column=0, sticky="w", pady=4)
        email = ttk.Entry(box, textvariable=self.email_var, width=34)
        email.grid(row=1, column=1, pady=4)
        ttk.Label(box, text="Contraseña").grid(row=2, column=0, sticky="w", pady=4)
        password = ttk.Entry(box, textvariable=self.password_var, width=34, show="•")
        password.grid(row=2, column=1, pady=4)
        self.button = ttk.Button(box, text="Entrar", command=self.login)
        self.button.grid(row=3, column=0, columnspan=2, pady=(12, 0), sticky="ew")
        ttk.Label(box, text="La sesión (tokens) solo se guarda en memoria.", foreground="#666").grid(
            row=4, column=0, columnspan=2, pady=(10, 0))
        password.bind("<Return>", lambda _e: self.login())
        email.bind("<Return>", lambda _e: password.focus_set())
        email.focus_set()

    def login(self) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get()
        self.password_var.set("")  # never keep the password in the widget
        if not email or not password:
            self.ctx.info("Datos incompletos", "Escribe tu email y tu contraseña.")
            return
        self.button.configure(state="disabled")

        def failed(exc):
            self.button.configure(state="normal")
            self.ctx.show_error(exc, "No se pudo iniciar sesión")

        def succeeded(user):
            self.button.configure(state="normal")
            self.on_logged_in(user)

        self.ctx.run(lambda: self.ctx.api.auth.login(email, password), succeeded, busy="Iniciando sesión...", on_error=failed)
