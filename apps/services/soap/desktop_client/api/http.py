"""
Reusable HTTP layer for every microservice (stdlib only: urllib + json).

- One place for base URLs, timeouts, JSON, headers and the Bearer token.
- Normalizes the three error shapes used by the backend:
    {"success": false, "code", "message", "details"}   users/authors/orders/payments,
                                                       and 401/403/503 of login
    {"success": false, "message"}                      other login errors
    {"error": {"code", "message"}}                     books
  into one ApiError(status, code, message, details, service).
- Network failures (service down, timeout, DNS) -> ServiceUnreachableError;
  the application never crashes because a service is offline.
- Automatic refresh: a protected request answered 401 triggers ONE
  POST /refresh (rotation) and ONE retry of the original request. If the
  refresh is rejected, the local session is cleared and
  SessionExpiredError is raised. A retried request that still gets 401
  never refreshes again (no loops).

Tokens are never logged; error messages never include them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import socket
import threading
from typing import Any, Callable
from urllib import error, parse, request

from api.session import Session


logger = logging.getLogger("desktop_client.http")

# Services whose JSON must be requested explicitly (they answer XML by default).
FORMAT_JSON_SERVICES = frozenset({"books", "login"})

SERVICE_LABELS = {
    "books": "Books",
    "login": "Login",
    "users": "Users",
    "authors": "Authors",
    "orders": "Orders",
    "payments": "Payments",
}

_DEFAULT_CODES = {
    400: "INVALID_INPUT",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    503: "SERVICE_UNAVAILABLE",
}


@dataclass
class ApiError(Exception):
    status: int | None
    code: str
    message: str
    service: str
    details: dict | None = field(default=None)

    def __str__(self) -> str:
        return f"{self.service}: {self.code} ({self.status}) {self.message}"


class ServiceUnreachableError(ApiError):
    """Connection refused, timeout, DNS... the service did not answer at all."""


class SessionExpiredError(ApiError):
    """The session cannot be used anymore (refresh rejected): log in again."""


@dataclass(frozen=True)
class RawResponse:
    status: int
    body: bytes


Transport = Callable[[str, str, dict, bytes | None, float], RawResponse]


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> RawResponse:
    """
    `timeout` bounds the connection AND every blocking read (urllib applies
    the socket timeout to both), so a request can never hang forever.
    """
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return RawResponse(response.status, response.read())
    except error.HTTPError as exc:
        return RawResponse(exc.code, exc.read())


class ApiClient:
    def __init__(
        self,
        session: Session,
        base_urls: dict[str, str],
        *,
        timeout: float = 10.0,
        transport: Transport | None = None,
        on_session_expired: Callable[[], None] | None = None,
    ) -> None:
        self.session = session
        self.base_urls = dict(base_urls)
        self.timeout = timeout
        self._transport = transport or urllib_transport
        self.on_session_expired = on_session_expired
        self._refresh_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, service: str, path: str, **kwargs) -> Any:
        return self.request(service, "GET", path, **kwargs)

    def post(self, service: str, path: str, **kwargs) -> Any:
        return self.request(service, "POST", path, **kwargs)

    def put(self, service: str, path: str, **kwargs) -> Any:
        return self.request(service, "PUT", path, **kwargs)

    def patch(self, service: str, path: str, **kwargs) -> Any:
        return self.request(service, "PATCH", path, **kwargs)

    def delete(self, service: str, path: str, **kwargs) -> Any:
        return self.request(service, "DELETE", path, **kwargs)

    def request(
        self,
        service: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        auth: bool = True,
        bearer: str | None = None,
        timeout: float | None = None,
        _retry: bool = True,
    ) -> Any:
        """
        auth=True  -> sends the session's access token (refresh on 401).
        bearer=... -> sends exactly that token (used by /refresh), no refresh.
        Returns the decoded JSON body (or None for an empty body).
        """
        token = bearer
        if auth and bearer is None:
            token = self.session.access_token
            if token is None:
                raise SessionExpiredError(401, "NOT_LOGGED_IN", "No active session.", service)

        response = self._send(service, method, path, json_body, params, token, timeout)

        if response.status == 401 and auth and bearer is None:
            if _retry and self._refresh(token_used=token):
                return self.request(service, method, path, json_body=json_body, params=params,
                                    auth=auth, timeout=timeout, _retry=False)
            if not _retry:
                # Even a freshly refreshed token was refused: give up, no loop.
                self._expire()
            raise SessionExpiredError(401, "SESSION_EXPIRED", "Your session has expired. Please log in again.", service)

        if response.status >= 400:
            raise self._error(service, path, response)
        return self._decode(service, response)

    def probe(self, service: str, path: str, *, params: dict | None = None, timeout: float | None = None) -> RawResponse:
        """
        Unauthenticated GET returning the raw response WITHOUT raising on
        4xx/5xx (used by health checks, where a 503 body is meaningful).
        Raises ServiceUnreachableError if the service does not answer.
        """
        return self._send(service, "GET", path, None, params, None, timeout)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _url(self, service: str, path: str, params: dict[str, Any] | None) -> str:
        query = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        if service in FORMAT_JSON_SERVICES:
            query.setdefault("format", "json")
        url = self.base_urls[service] + path
        return f"{url}?{parse.urlencode(query)}" if query else url

    def _send(self, service, method, path, json_body, params, token, timeout) -> RawResponse:
        headers = {"Accept": "application/json"}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = self._url(service, path, params)
        try:
            return self._transport(method, url, headers, body, timeout or self.timeout)
        except (error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            # Only the exception type is logged: never headers or tokens.
            logger.warning("%s %s %s unreachable (%s)", service, method, path, type(exc).__name__)
            label = SERVICE_LABELS.get(service, service)
            raise ServiceUnreachableError(
                None, "SERVICE_UNREACHABLE", f"{label} service is currently unavailable.", service
            ) from None

    @staticmethod
    def _parse_json(response: RawResponse) -> Any:
        if not response.body:
            return None
        try:
            return json.loads(response.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _decode(self, service: str, response: RawResponse) -> Any:
        data = self._parse_json(response)
        if data is None and response.body:
            raise ApiError(response.status, "INVALID_RESPONSE", "The service returned a non-JSON response.", service)
        return data

    def _error(self, service: str, path: str, response: RawResponse) -> ApiError:
        data = self._parse_json(response)
        code = message = None
        details = None
        if isinstance(data, dict):
            if isinstance(data.get("error"), dict):  # Books
                code = data["error"].get("code")
                message = data["error"].get("message")
            else:
                code = data.get("code")
                message = data.get("message")
                details = data.get("details") if isinstance(data.get("details"), dict) else None
        if service == "login" and path == "/login" and response.status == 401 and not code:
            code = "INVALID_CREDENTIALS"
        code = code or _DEFAULT_CODES.get(response.status, f"HTTP_{response.status}")
        message = message or f"HTTP {response.status}"
        return ApiError(response.status, code, message, service, details)

    def _refresh(self, token_used: str | None) -> bool:
        """
        Serialized: if several threads get 401 at once, only the first one
        calls /refresh (the refresh token is single-use, it rotates); the
        others see the new access token and just retry.
        Returns True when a new access token is available.
        Network/5xx failures raise (the session is kept: it may still be valid).
        """
        with self._refresh_lock:
            current = self.session.access_token
            if current is not None and current != token_used:
                return True
            refresh_token = self.session.refresh_token
            if not refresh_token:
                self._expire()
                return False
            try:
                data = self.request("login", "POST", "/refresh", auth=False, bearer=refresh_token)
            except ServiceUnreachableError:
                raise
            except ApiError as exc:
                if exc.status is not None and exc.status >= 500:
                    raise
                self._expire()
                return False

            if not isinstance(data, dict) or not data.get("access_token") or not data.get("refresh_token"):
                self._expire()
                return False
            self.session.update_tokens(data["access_token"], data["refresh_token"], data.get("user"))
            logger.info("Access token refreshed")
            return True

    def _expire(self) -> None:
        if self.session.is_authenticated:
            self.session.clear()
            if self.on_session_expired is not None:
                self.on_session_expired()
