from __future__ import annotations

import json
import logging
from typing import Any, Callable
from xml.etree import ElementTree as ET

from flask import Response, request

from utils.errors import ServiceError, internal_error, invalid_format


logger = logging.getLogger("login_microservice.responses")

SUPPORTED_FORMATS = {"xml", "json"}
DEFAULT_FORMAT = "xml"


def get_response_format() -> str:
    """
    Centralized format resolution, shared by every endpoint.

    - No `format` query parameter, or an empty value -> "xml" (default).
    - `?format=xml` -> "xml".
    - `?format=json` -> "json".
    - Any other value -> ServiceError INVALID_FORMAT (400).
    """
    raw = request.args.get("format")

    if raw is None or not raw.strip():
        return DEFAULT_FORMAT

    value = raw.strip().lower()

    if value not in SUPPORTED_FORMATS:
        raise invalid_format()

    return value


def _append_xml(parent: ET.Element, key: str, value: Any) -> None:
    if isinstance(value, dict):
        node = ET.SubElement(parent, key)
        for child_key, child_value in value.items():
            _append_xml(node, child_key, child_value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _append_xml(parent, key, item)
    elif isinstance(value, bool):
        node = ET.SubElement(parent, key)
        node.text = "true" if value else "false"
    elif value is None:
        ET.SubElement(parent, key)
    else:
        node = ET.SubElement(parent, key)
        node.text = str(value)


def to_xml_bytes(root_name: str, data: dict) -> bytes:
    """
    Generic dict -> XML serializer shared by every endpoint, so the same
    payload structure only needs to be built once (as a dict) and can be
    rendered as either XML or JSON without duplicating logic per endpoint.
    """
    root = ET.Element(root_name)
    for key, value in data.items():
        _append_xml(root, key, value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def respond(response_format: str, status: int, data: dict, root_name: str = "response") -> Response:
    if response_format == "json":
        return Response(json.dumps(data), status=status, mimetype="application/json")

    return Response(to_xml_bytes(root_name, data), status=status, mimetype="application/xml")


def error_response(error: ServiceError, response_format: str) -> Response:
    payload = {"success": False, "message": error.message}
    return respond(response_format, error.http_status, payload)


# BuildResponse: (response_format: str) -> (status, json_serializable_payload)
BuildResponse = Callable[[str], tuple[int, dict]]


def service_route(build_response: BuildResponse) -> Response:
    """
    Shared entry point for every REST endpoint of the login microservice:

      1. resolves `format` once;
      2. runs the endpoint-specific callback, which only talks to
         services/repositories and returns a plain dict payload;
      3. maps any ServiceError, or an unexpected exception, to a safe,
         XML/JSON error response instead of letting Flask render HTML.

    No endpoint re-implements format resolution, error handling or
    serialization.
    """
    try:
        response_format = get_response_format()
    except ServiceError as exc:
        # The format itself could not be resolved: fall back to the
        # documented default (XML) to render this specific error.
        return error_response(exc, DEFAULT_FORMAT)

    try:
        status, payload = build_response(response_format)
        return respond(response_format, status, payload)
    except ServiceError as exc:
        return error_response(exc, response_format)
    except Exception:
        logger.exception("Unexpected error in login microservice endpoint")
        return error_response(internal_error(), response_format)
