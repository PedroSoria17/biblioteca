"""
Fake HTTP transport for the desktop client tests: no service is started,
no socket is opened. Each test registers handlers by (method, path).
"""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs, urlsplit

from api import LibraryApi
from api.http import RawResponse
from client_config import load_config


# Expected warnings (unreachable fakes) would only add noise to the test output.
logging.getLogger("desktop_client").setLevel(logging.ERROR)

CONFIG = load_config(env={}, env_file=None)  # local defaults, no .env


def ok(payload, status=200) -> RawResponse:
    return RawResponse(status, json.dumps(payload).encode("utf-8"))


def err(status, code=None, message="error", details=None, shape="std") -> RawResponse:
    if shape == "books":
        body = {"error": {"code": code, "message": message}}
    elif shape == "login":
        body = {"success": False, "message": message}
    else:
        body = {"success": False, "code": code, "message": message}
        if details:
            body["details"] = details
    return RawResponse(status, json.dumps(body).encode("utf-8"))


class Call:
    def __init__(self, method, url, headers, body, timeout):
        parts = urlsplit(url)
        self.method = method
        self.url = url
        self.base = f"{parts.scheme}://{parts.netloc}"
        self.path = parts.path
        self.query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.headers = headers
        self.json = json.loads(body.decode("utf-8")) if body else None
        self.timeout = timeout

    @property
    def bearer(self):
        value = self.headers.get("Authorization", "")
        return value[7:] if value.startswith("Bearer ") else None


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[Call] = []
        self.handlers: dict[tuple[str, str], object] = {}
        self.down_hosts: set[str] = set()

    def on(self, method: str, path: str, response) -> None:
        """`response` is a RawResponse, a list of them (consumed in order) or a callable(call)."""
        self.handlers[(method, path)] = response

    def __call__(self, method, url, headers, body, timeout):
        call = Call(method, url, headers, body, timeout)
        self.calls.append(call)
        if call.base in self.down_hosts:
            raise ConnectionRefusedError("refused")
        handler = self.handlers.get((method, call.path))
        if handler is None:
            return err(404, "NOT_FOUND", f"no fake for {method} {call.path}")
        if isinstance(handler, list):
            return handler.pop(0) if len(handler) > 1 else handler[0]
        if callable(handler):
            return handler(call)
        return handler

    def paths(self) -> list[str]:
        return [f"{c.method} {c.path}" for c in self.calls]


def make_api(on_session_expired=None):
    transport = FakeTransport()
    api = LibraryApi(CONFIG, transport=transport, on_session_expired=on_session_expired)
    return api, transport


LOGIN_OK = {
    "success": True,
    "message": "Login successful",
    "user": {"id": 7, "email": "ana@example.com", "role_id": 1},
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "token_type": "Bearer",
    "expires_in": 1200,
}


def logged_in(role_id=1):
    api, transport = make_api()
    api.session.start("access-1", "refresh-1", {"id": 7, "email": "ana@example.com", "role_id": role_id})
    return api, transport
