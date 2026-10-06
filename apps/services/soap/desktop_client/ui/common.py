"""
Shared Tkinter helpers.

Threading rule of the whole client: HTTP calls run in worker threads and
NEVER touch widgets. Workers hand their results to UiDispatcher, a queue
that the Tk main loop drains every few milliseconds (root.after), so every
widget update happens in the main thread.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from api.errors import friendly_message
from api.http import SessionExpiredError


class UiDispatcher:
    POLL_MS = 40

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._closed = False
        self._after_id = self.root.after(self.POLL_MS, self._drain)

    def call_soon(self, fn: Callable[[], None]) -> None:
        """Thread-safe: schedule `fn` to run in the Tk main thread."""
        if not self._closed:
            self._queue.put(fn)

    def _drain(self) -> None:
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                break
            fn()
        if not self._closed:
            self._after_id = self.root.after(self.POLL_MS, self._drain)

    def close(self) -> None:
        """Stops polling (call before destroying the root window)."""
        self._closed = True
        try:
            self.root.after_cancel(self._after_id)
        except tk.TclError:
            pass


class AppContext:
    """What every tab needs: the API, the dispatcher and error reporting."""

    def __init__(self, root, api, dispatcher: UiDispatcher, cart, on_session_expired: Callable[[], None]) -> None:
        self.root = root
        self.api = api
        self.dispatcher = dispatcher
        self.cart = cart
        self.on_session_expired = on_session_expired
        self.status_var = tk.StringVar(master=root, value="Listo.")

    @property
    def role_id(self) -> int | None:
        user = self.api.session.user
        return user.role_id if user else None

    def run(
        self,
        work: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        *,
        busy: str | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        """Runs `work` in a worker thread; callbacks run in the main thread."""
        if busy:
            self.status_var.set(busy)
        self.root.configure(cursor="watch")

        def worker():
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 - reported to the user
                # Bind exc now: Python deletes the name when the except block ends.
                self.dispatcher.call_soon(lambda e=exc: self._failed(e, on_error))
            else:
                self.dispatcher.call_soon(lambda r=result: self._succeeded(r, on_success))

        threading.Thread(target=worker, daemon=True).start()

    def _succeeded(self, result, on_success) -> None:
        self.root.configure(cursor="")
        self.status_var.set("Listo.")
        if on_success is not None:
            on_success(result)

    def _failed(self, exc: BaseException, on_error) -> None:
        self.root.configure(cursor="")
        if isinstance(exc, SessionExpiredError):
            self.status_var.set("Sesión expirada.")
            messagebox.showwarning("Sesión expirada", friendly_message(exc), parent=self.root)
            self.on_session_expired()
            return
        if on_error is not None:
            on_error(exc)
            return
        self.show_error(exc)

    def show_error(self, exc: BaseException, title: str = "Error") -> None:
        message = friendly_message(exc)
        self.status_var.set(message.splitlines()[0])
        messagebox.showerror(title, message, parent=self.root)

    def info(self, title: str, message: str) -> None:
        self.status_var.set(message.splitlines()[0])
        messagebox.showinfo(title, message, parent=self.root)

    def confirm(self, title: str, message: str) -> bool:
        return messagebox.askyesno(title, message, parent=self.root)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class Table(ttk.Frame):
    """Treeview + scrollbar keeping the row dicts by item id."""

    def __init__(self, parent, columns: list[tuple[str, str, int]], height: int = 12) -> None:
        super().__init__(parent)
        self.keys = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=self.keys, show="headings", selectmode="browse", height=height)
        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=40, anchor="w")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._rows: dict[str, dict] = {}

    def set_rows(self, rows: list[dict], tag_for: Callable[[dict], str | None] | None = None) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for row in rows:
            values = ["" if row.get(k) is None else row.get(k) for k in self.keys]
            tags = (tag_for(row),) if tag_for and tag_for(row) else ()
            item = self.tree.insert("", "end", values=values, tags=tags)
            self._rows[item] = row

    def selected(self) -> dict | None:
        selection = self.tree.selection()
        return self._rows.get(selection[0]) if selection else None

    def bind_select(self, callback: Callable[[], None]) -> None:
        self.tree.bind("<<TreeviewSelect>>", lambda _e: callback())

    def rows(self) -> list[dict]:
        return list(self._rows.values())


class FormDialog(tk.Toplevel):
    """
    Modal form. fields: list of dicts with
      key, label, kind ('text'|'password'|'int'|'combo'|'check'),
      initial, options (combo), required (bool), optional_blank (bool).
    `result` is None if cancelled, else {key: value} (only validated types).
    """

    def __init__(self, parent, title: str, fields: list[dict], submit_text: str = "Guardar") -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: dict | None = None
        self._fields = fields
        self._vars: dict[str, tk.Variable] = {}

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        for row, spec in enumerate(fields):
            ttk.Label(body, text=spec["label"]).grid(row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            kind = spec.get("kind", "text")
            initial = spec.get("initial")
            if kind == "check":
                var = tk.BooleanVar(self, value=bool(initial))
                ttk.Checkbutton(body, variable=var).grid(row=row, column=1, sticky="w")
            elif kind == "combo":
                var = tk.StringVar(self, value="" if initial is None else str(initial))
                ttk.Combobox(body, textvariable=var, values=spec["options"], state="readonly", width=32).grid(
                    row=row, column=1, sticky="ew")
            else:
                var = tk.StringVar(self, value="" if initial is None else str(initial))
                ttk.Entry(body, textvariable=var, width=36, show="•" if kind == "password" else "").grid(
                    row=row, column=1, sticky="ew")
            self._vars[spec["key"]] = var

        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text=submit_text, command=self._submit).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _e: self._submit())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _submit(self) -> None:
        values: dict[str, Any] = {}
        try:
            for spec in self._fields:
                kind = spec.get("kind", "text")
                raw = self._vars[spec["key"]].get()
                if kind == "check":
                    values[spec["key"]] = bool(raw)
                    continue
                raw = str(raw).strip() if kind != "password" else str(raw)
                if raw == "":
                    if spec.get("required", True):
                        raise ValueError(f"'{spec['label']}' es obligatorio.")
                    values[spec["key"]] = None
                    continue
                if kind == "int":
                    try:
                        values[spec["key"]] = int(raw)
                    except ValueError as exc:
                        raise ValueError(f"'{spec['label']}' debe ser un número entero.") from exc
                else:
                    values[spec["key"]] = raw
        except ValueError as exc:
            messagebox.showwarning("Datos inválidos", str(exc), parent=self)
            return
        self.result = values
        self.destroy()

    @classmethod
    def ask(cls, parent, title: str, fields: list[dict], submit_text: str = "Guardar") -> dict | None:
        dialog = cls(parent, title, fields, submit_text)
        parent.wait_window(dialog)
        return dialog.result


def changed_fields(original: dict, edited: dict) -> dict:
    """Only what the user actually changed (PATCH bodies)."""
    return {k: v for k, v in edited.items() if original.get(k) != v}
