from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from soap_client import LibrarySoapClient, SoapFaultError


class LibraryClassifierApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Library Cloud Classifier — SOAP Client")
        self.geometry("1180x720")
        self.minsize(980, 620)

        self.pending_by_item: dict[str, dict] = {}

        self.endpoint_var = tk.StringVar(
            value="http://127.0.0.1:5000/soap"
        )
        self.nombre_var = tk.StringVar(value="Pedro")
        self.apellidos_var = tk.StringVar(value="Soria")
        self.correo_var = tk.StringVar(
            value="pedro.soap.test@udem.edu"
        )
        self.modelo_var = tk.StringVar(value="IaaS")
        self.limite_var = tk.IntVar(value=20)

        self.progreso_var = tk.StringVar(
            value="Progreso: sin consultar"
        )
        self.estado_var = tk.StringVar(
            value="Listo. Verifica que Flask esté ejecutándose."
        )

        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        title = ttk.Label(
            container,
            text="Cloud Computing Concept Classifier",
            font=("Segoe UI", 18, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            container,
            text="Desktop SOAP client · Exercise 03",
        )
        subtitle.pack(anchor="w", pady=(0, 14))

        config = ttk.LabelFrame(
            container,
            text="Service and classifier",
            padding=12,
        )
        config.pack(fill="x")

        ttk.Label(config, text="SOAP endpoint").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(
            config,
            textvariable=self.endpoint_var,
            width=50,
        ).grid(
            row=0,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=(8, 16),
        )

        ttk.Label(config, text="Pending limit").grid(
            row=0, column=4, sticky="w"
        )
        ttk.Spinbox(
            config,
            from_=1,
            to=100,
            textvariable=self.limite_var,
            width=8,
        ).grid(row=0, column=5, sticky="w", padx=(8, 0))

        ttk.Label(config, text="First name").grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Entry(
            config,
            textvariable=self.nombre_var,
            width=22,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(8, 16),
            pady=(10, 0),
        )

        ttk.Label(config, text="Last name(s)").grid(
            row=1, column=2, sticky="w", pady=(10, 0)
        )
        ttk.Entry(
            config,
            textvariable=self.apellidos_var,
            width=24,
        ).grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(8, 16),
            pady=(10, 0),
        )

        ttk.Label(config, text="Email").grid(
            row=1, column=4, sticky="w", pady=(10, 0)
        )
        ttk.Entry(
            config,
            textvariable=self.correo_var,
            width=30,
        ).grid(
            row=1,
            column=5,
            sticky="ew",
            padx=(8, 0),
            pady=(10, 0),
        )

        for col in (1, 3, 5):
            config.columnconfigure(col, weight=1)

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=12)

        self.load_button = ttk.Button(
            actions,
            text="Load pending concepts",
            command=self.load_pending,
        )
        self.load_button.pack(side="left")

        self.progress_button = ttk.Button(
            actions,
            text="Refresh progress",
            command=self.refresh_progress,
        )
        self.progress_button.pack(side="left", padx=(8, 0))

        ttk.Label(
            actions,
            textvariable=self.progreso_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        content = ttk.Panedwindow(
            container,
            orient="vertical",
        )
        content.pack(fill="both", expand=True)

        table_frame = ttk.LabelFrame(
            content,
            text="Pending concepts",
            padding=8,
        )
        content.add(table_frame, weight=3)

        columns = (
            "isbn",
            "title",
            "category",
            "concept_id",
            "concept",
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        headings = {
            "isbn": "ISBN",
            "title": "Book",
            "category": "Category",
            "concept_id": "ID",
            "concept": "Concept",
        }

        widths = {
            "isbn": 130,
            "title": 290,
            "category": 130,
            "concept_id": 70,
            "concept": 220,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(
                col,
                width=widths[col],
                minwidth=60,
            )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(
            side="left",
            fill="both",
            expand=True,
        )
        scrollbar.pack(side="right", fill="y")

        self.tree.bind(
            "<<TreeviewSelect>>",
            self.on_selection_changed,
        )

        detail_frame = ttk.LabelFrame(
            content,
            text="Selected concept",
            padding=10,
        )
        content.add(detail_frame, weight=2)

        top_detail = ttk.Frame(detail_frame)
        top_detail.pack(fill="x")

        ttk.Label(top_detail, text="Cloud model").pack(
            side="left"
        )

        model_combo = ttk.Combobox(
            top_detail,
            textvariable=self.modelo_var,
            values=("IaaS", "PaaS", "SaaS", "FaaS"),
            state="readonly",
            width=10,
        )
        model_combo.pack(side="left", padx=(8, 12))

        self.classify_button = ttk.Button(
            top_detail,
            text="Register classification",
            command=self.register_classification,
            state="disabled",
        )
        self.classify_button.pack(side="left")

        self.selected_label = ttk.Label(
            top_detail,
            text="No concept selected",
        )
        self.selected_label.pack(
            side="left",
            padx=(16, 0),
        )

        ttk.Label(
            detail_frame,
            text="Definition",
        ).pack(anchor="w", pady=(10, 4))

        self.definition_text = tk.Text(
            detail_frame,
            height=6,
            wrap="word",
        )
        self.definition_text.pack(fill="both", expand=True)
        self.definition_text.configure(state="disabled")

        status = ttk.Label(
            container,
            textvariable=self.estado_var,
            relief="sunken",
            anchor="w",
            padding=(8, 5),
        )
        status.pack(fill="x", pady=(12, 0))

    def _client(self) -> LibrarySoapClient:
        endpoint = self.endpoint_var.get().strip()

        if not endpoint:
            raise ValueError("SOAP endpoint is required.")

        return LibrarySoapClient(endpoint)

    def _classifier(self) -> dict[str, str]:
        values = {
            "nombre": self.nombre_var.get().strip(),
            "apellidos": self.apellidos_var.get().strip(),
            "correo": self.correo_var.get().strip(),
        }

        if not all(values.values()):
            raise ValueError(
                "First name, last name(s), and email are required."
            )

        return values

    def _run_async(self, action, on_success) -> None:
        self.config(cursor="watch")

        def worker():
            try:
                result = action()
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._show_error(exc),
                )
            else:
                self.after(
                    0,
                    lambda: on_success(result),
                )
            finally:
                self.after(
                    0,
                    lambda: self.config(cursor=""),
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _show_error(self, exc: Exception) -> None:
        if isinstance(exc, SoapFaultError):
            self.estado_var.set(
                f"SOAP Fault HTTP {exc.http_status}: "
                f"{exc.code} — {exc.message}"
            )
            messagebox.showerror(
                "SOAP Fault",
                f"HTTP {exc.http_status}\n\n"
                f"Code: {exc.code}\n"
                f"Message: {exc.message}",
            )
        else:
            self.estado_var.set(str(exc))
            messagebox.showerror("Error", str(exc))

    def load_pending(self) -> None:
        try:
            classifier = self._classifier()
            client = self._client()
            limit = int(self.limite_var.get())
        except Exception as exc:
            self._show_error(exc)
            return

        self.estado_var.set("Loading pending concepts...")

        self._run_async(
            lambda: client.obtener_conceptos_pendientes(
                **classifier,
                limite=limit,
            ),
            self._render_pending,
        )

    def _render_pending(self, rows: list[dict]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.pending_by_item.clear()
        self.classify_button.configure(state="disabled")
        self._set_definition("")
        self.selected_label.configure(
            text="No concept selected"
        )

        for row in rows:
            item_id = self.tree.insert(
                "",
                "end",
                values=(
                    row["isbn"],
                    row["titulo"],
                    row["categoria"],
                    row["concepto_id"],
                    row["concepto"],
                ),
            )
            self.pending_by_item[item_id] = row

        self.estado_var.set(
            f"{len(rows)} pending concept(s) loaded."
        )

        self.refresh_progress()

    def on_selection_changed(self, _event=None) -> None:
        selected = self.tree.selection()

        if not selected:
            self.classify_button.configure(state="disabled")
            return

        row = self.pending_by_item.get(selected[0])

        if row is None:
            return

        self.selected_label.configure(
            text=f'{row["concepto"]} · {row["isbn"]}'
        )
        self._set_definition(row["definicion"])
        self.classify_button.configure(state="normal")

    def _set_definition(self, text: str) -> None:
        self.definition_text.configure(state="normal")
        self.definition_text.delete("1.0", "end")
        self.definition_text.insert("1.0", text)
        self.definition_text.configure(state="disabled")

    def register_classification(self) -> None:
        selected = self.tree.selection()

        if not selected:
            messagebox.showwarning(
                "Selection required",
                "Select a concept first.",
            )
            return

        row = self.pending_by_item[selected[0]]

        try:
            classifier = self._classifier()
            client = self._client()
        except Exception as exc:
            self._show_error(exc)
            return

        model = self.modelo_var.get()

        self.estado_var.set(
            f"Registering {row['concepto']} as {model}..."
        )

        self._run_async(
            lambda: client.registrar_clasificacion(
                **classifier,
                isbn=row["isbn"],
                concepto_id=row["concepto_id"],
                modelo_cloud=model,
            ),
            lambda result: self._after_registration(
                result,
                row,
                selected[0],
            ),
        )

    def _after_registration(
        self,
        result: dict,
        row: dict,
        item_id: str,
    ) -> None:
        self.estado_var.set(result["mensaje"])

        messagebox.showinfo(
            "Classification registered",
            f'{row["concepto"]} → {self.modelo_var.get()}\n\n'
            f'{result["mensaje"]}\n'
            f'Date: {result["fecha"]}',
        )

        if self.tree.exists(item_id):
            self.tree.delete(item_id)

        self.pending_by_item.pop(item_id, None)
        self.classify_button.configure(state="disabled")
        self.selected_label.configure(
            text="No concept selected"
        )
        self._set_definition("")

        self.refresh_progress()

    def refresh_progress(self) -> None:
        correo = self.correo_var.get().strip()

        if not correo:
            self._show_error(
                ValueError("Email is required.")
            )
            return

        try:
            client = self._client()
        except Exception as exc:
            self._show_error(exc)
            return

        self._run_async(
            lambda: client.obtener_progreso_usuario(
                correo=correo,
            ),
            self._render_progress,
        )

    def _render_progress(self, result: dict) -> None:
        self.progreso_var.set(
            "Progress: "
            f'{result["total_clasificados"]}/'
            f'{result["total_catalogo"]} '
            f'({result["porcentaje"]}%) · '
            f'{result["total_pendientes"]} pending'
        )


if __name__ == "__main__":
    app = LibraryClassifierApp()
    app.mainloop()
