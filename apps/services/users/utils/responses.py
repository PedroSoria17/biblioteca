from __future__ import annotations

from typing import Any

from flask import Response, jsonify

from utils.errors import ServiceError


def ok(data: Any, status: int = 200, **extra: Any) -> Response:
    payload = {"success": True, "data": data, **extra}
    response = jsonify(payload)
    response.status_code = status
    return response


def error_response(error: ServiceError) -> Response:
    payload: dict[str, Any] = {"success": False, "code": error.code, "message": error.message}
    if error.details:
        payload["details"] = error.details
    response = jsonify(payload)
    response.status_code = error.http_status
    return response
