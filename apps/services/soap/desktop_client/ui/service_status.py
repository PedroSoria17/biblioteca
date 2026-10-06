"""
Microservice "traffic lights" (GET /health of the six services).

Checks run in ONE background thread (the six requests in parallel, 3 s
timeout each), never in the Tk thread. Refreshed on demand ("Refresh
Services") and every HEALTH_REFRESH_SECONDS (60 s by default); a new check
is not started while the previous one is still running.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from api.health import DEGRADED, DOWN, UP
from api.http import SERVICE_LABELS
from client_config import SERVICES


COLORS = {UP: "#2e9e44", DEGRADED: "#e0a100", DOWN: "#c62828", None: "#9e9e9e"}
TEXT = {UP: "disponible", DEGRADED: "degradado", DOWN: "no disponible", None: "sin consultar"}


class ServiceStatusBar(ttk.Frame):
    def __init__(self, parent, api, dispatcher, refresh_seconds: int) -> None:
        super().__init__(parent, padding=(0, 4))
        self.api = api
        self.dispatcher = dispatcher
        self.refresh_ms = refresh_seconds * 1000
        self._checking = False
        self._after_id = None
        self.lights: dict[str, tuple[tk.Canvas, ttk.Label]] = {}

        ttk.Label(self, text="Servicios:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        for service in SERVICES:
            box = ttk.Frame(self)
            box.pack(side="left", padx=(0, 12))
            canvas = tk.Canvas(box, width=14, height=14, highlightthickness=0)
            canvas.create_oval(2, 2, 12, 12, fill=COLORS[None], outline="", tags="dot")
            canvas.pack(side="left")
            label = ttk.Label(box, text=f"{SERVICE_LABELS[service]}")
            label.pack(side="left", padx=(3, 0))
            self.lights[service] = (canvas, label)

        self.button = ttk.Button(self, text="Refresh Services", command=self.refresh)
        self.button.pack(side="right")
        self.summary = ttk.Label(self, text="")
        self.summary.pack(side="right", padx=8)

    def refresh(self) -> None:
        if self._checking:
            return
        self._checking = True
        self.button.configure(state="disabled")

        def worker():
            results = self.api.health.check_all(SERVICES)
            self.dispatcher.call_soon(lambda: self._show(results))

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, results) -> None:
        self._checking = False
        if not self.winfo_exists():
            return
        self.button.configure(state="normal")
        for health in results:
            canvas, label = self.lights[health.service]
            canvas.itemconfigure("dot", fill=COLORS[health.state])
            # Text as well as color (readable without distinguishing colors).
            suffix = {UP: "", DEGRADED: " (degradado)", DOWN: " (caído)"}[health.state]
            label.configure(text=f"{SERVICE_LABELS[health.service]}{suffix}")
            _Tooltip.attach(label, f"{SERVICE_LABELS[health.service]}: {TEXT[health.state]} ({health.detail})")
        up = sum(1 for h in results if h.state == UP)
        self.summary.configure(text=f"{up}/{len(results)} disponibles")
        self._schedule()

    def start(self) -> None:
        self.refresh()

    def _schedule(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = self.after(self.refresh_ms, self.refresh)

    def destroy(self) -> None:
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        super().destroy()


class _Tooltip:
    """Minimal hover text (state + database/redis detail)."""

    @staticmethod
    def attach(widget, text: str) -> None:
        widget._tooltip_text = text
        if getattr(widget, "_tooltip_bound", False):
            return
        widget._tooltip_bound = True
        widget._tooltip_window = None

        def show(_event):
            if widget._tooltip_window is not None:
                return
            window = tk.Toplevel(widget)
            window.wm_overrideredirect(True)
            window.wm_geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + 20}")
            ttk.Label(window, text=widget._tooltip_text, relief="solid", padding=4, background="#ffffe0").pack()
            widget._tooltip_window = window

        def hide(_event):
            if widget._tooltip_window is not None:
                widget._tooltip_window.destroy()
                widget._tooltip_window = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)
