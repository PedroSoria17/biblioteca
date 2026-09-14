from __future__ import annotations

from flask import Request

from catalog.errors import invalid_format


SUPPORTED_FORMATS = {"xml", "json"}
DEFAULT_FORMAT = "xml"


def get_response_format(request: Request) -> str:
    """
    Centralized format resolution for every REST catalog endpoint.

    Rule (documented in README):
      - No `format` query parameter, or an empty value -> "xml" (default).
      - `?format=xml` -> "xml".
      - `?format=json` -> "json".
      - Any other value (e.g. `?format=csv`) -> CatalogError INVALID_FORMAT (400).
    """
    raw = request.args.get("format")

    if raw is None or not raw.strip():
        return DEFAULT_FORMAT

    value = raw.strip().lower()

    if value not in SUPPORTED_FORMATS:
        raise invalid_format()

    return value
