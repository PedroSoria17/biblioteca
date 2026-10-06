"""
Library desktop client: Tkinter front-end for the six microservices.

    Books/SOAP :5000 · Login :5001 · Users :5002 · Authors :5003 · Orders :5004 · Payments :5005

Run from this folder:  python main.py
URLs come from environment variables or desktop_client/.env (see .env.example).
The original SOAP classifier is still available alone: python desktop_app.py
"""

from __future__ import annotations

import logging
import sys

from client_config import ConfigError, load_config


def main() -> None:
    # Never DEBUG: request details are not logged anyway, but keep it quiet.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    try:
        config = load_config()
    except ConfigError as exc:
        sys.exit(f"Configuración inválida: {exc}")

    from ui.app import MainApp

    MainApp(config).mainloop()


if __name__ == "__main__":
    main()
