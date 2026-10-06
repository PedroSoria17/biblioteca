from __future__ import annotations

import json
import logging
from typing import Any, Callable

from flask import Response, request
from library_shared.errors import AuthError

from catalog.errors import CatalogError, internal_error
from catalog.format import get_response_format
from catalog.serializers import error_to_dict, error_to_xml


logger = logging.getLogger("library_soap_service.catalog")


def respond(response_format: str, status: int, json_payload: Any, xml_bytes: bytes) -> Response:
    if response_format == "json":
        return Response(json.dumps(json_payload), status=status, mimetype="application/json")

    return Response(xml_bytes, status=status, mimetype="application/xml")


def error_response(error: CatalogError, response_format: str) -> Response:
    if response_format == "json":
        return respond("json", error.http_status, error_to_dict(error.code, error.message), b"")

    return respond("xml", error.http_status, None, error_to_xml(error.code, error.message))


def auth_error_response(error: AuthError) -> Response:
    """
    Renderer passed to library_shared.flask_auth.init_auth: 401/403/503 from
    the JWT checks use the same <error><code/><message/> shape as every
    other catalog error.
    """
    try:
        response_format = get_response_format(request)
    except CatalogError:
        response_format = "xml"

    response = error_response(CatalogError(error.code, error.message, error.http_status), response_format)
    if error.http_status == 401:
        response.headers["WWW-Authenticate"] = 'Bearer realm="library"'
    return response


# BuildResponse: (response_format: str) -> tuple[status, json_payload, xml_bytes]
BuildResponse = Callable[[str], tuple[int, Any, bytes]]


def catalog_route(build_response: BuildResponse) -> Response:
    """
    Shared entry point for every REST catalog endpoint:

      1. resolves `format` once (catalog/format.py);
      2. runs the endpoint-specific callback, which only fetches data
         (catalog/repository.py) and serializes it (catalog/serializers.py);
      3. maps any CatalogError, or an unexpected exception, to a safe,
         bilingual error response.

    No endpoint re-implements format resolution or error serialization.
    """
    try:
        response_format = get_response_format(request)
    except CatalogError as exc:
        # The format itself could not be resolved: fall back to the
        # documented default (XML) to render this specific error.
        return error_response(exc, "xml")

    try:
        status, json_payload, xml_bytes = build_response(response_format)
        return respond(response_format, status, json_payload, xml_bytes)
    except CatalogError as exc:
        return error_response(exc, response_format)
    except Exception:
        logger.exception("Unexpected error in REST catalog endpoint")
        return error_response(internal_error(), response_format)
