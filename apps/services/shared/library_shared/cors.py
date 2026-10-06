from __future__ import annotations

import logging

from flask import Flask
from flask_cors import CORS

from library_shared.settings import CorsSettings


logger = logging.getLogger("library_shared.cors")

ALLOWED_HEADERS = ["Authorization", "Content-Type"]
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def init_cors(app: Flask, settings: CorsSettings, supports_credentials: bool = False) -> None:
    """
    Enables CORS only for the explicitly configured origins. With no
    origins configured nothing is enabled (same-origin only), which is the
    safe default. Bearer tokens travel in a header, so cookies/credentials
    are off unless a service explicitly needs them.
    """
    if not settings.allowed_origins:
        logger.info("CORS disabled: CORS_ALLOWED_ORIGINS is empty")
        return

    CORS(
        app,
        origins=list(settings.allowed_origins),
        allow_headers=ALLOWED_HEADERS,
        methods=ALLOWED_METHODS,
        supports_credentials=supports_credentials,
        max_age=600,
    )
    logger.info("CORS enabled for %d origin(s)", len(settings.allowed_origins))
