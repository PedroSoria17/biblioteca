from __future__ import annotations

import socket
import threading
import unittest

from api.errors import friendly_message
from api.http import ApiError, ServiceUnreachableError, SessionExpiredError
from api.session import Session
from fakes import LOGIN_OK, err, logged_in, make_api, ok


class SessionTests(unittest.TestCase):
    def test_start_update_clear(self):
        session = Session()
        session.start("a1", "r1", {"id": 3, "email": "x@example.com", "role_id": 2})
        self.assertTrue(session.is_authenticated)
        self.assertTrue(session.is_admin)
        self.assertEqual(session.user.role_name, "ADMIN")

        session.update_tokens("a2", "r2", {"id": 3, "email": "x@example.com", "role_id": 1})
        self.assertEqual((session.access_token, session.refresh_token), ("a2", "r2"))
        self.assertFalse(session.is_admin)  # role re-read on refresh

        session.clear()
        self.assertFalse(session.is_authenticated)
        self.assertIsNone(session.access_token)
        self.assertIsNone(session.refresh_token)
        self.assertIsNone(session.user)

    def test_repr_never_shows_tokens(self):
        session = Session()
        session.start("secret-access", "secret-refresh", {"id": 1, "email": "e", "role_id": 1})
        self.assertNotIn("secret", repr(session))

    def test_update_after_logout_does_not_resurrect(self):
        session = Session()
        session.update_tokens("a", "r")
        self.assertFalse(session.is_authenticated)


class ApiClientTests(unittest.TestCase):
    def test_login_stores_session_in_memory_and_uses_json(self):
        api, transport = make_api()
        transport.on("POST", "/login", ok(LOGIN_OK))

        user = api.auth.login("ana@example.com", "Password123")

        self.assertEqual((user.user_id, user.role_id, user.email), (7, 1, "ana@example.com"))
        self.assertEqual(api.session.access_token, "access-1")
        call = transport.calls[0]
        self.assertEqual(call.query, {"format": "json"})
        self.assertEqual(call.json, {"email": "ana@example.com", "password": "Password123"})
        self.assertIsNone(call.bearer)

    def test_wrong_credentials(self):
        api, transport = make_api()
        transport.on("POST", "/login", err(401, message="Invalid credentials", shape="login"))

        with self.assertRaises(ApiError) as ctx:
            api.auth.login("a@b.com", "bad")

        self.assertEqual(ctx.exception.code, "INVALID_CREDENTIALS")
        self.assertIn("incorrectos", friendly_message(ctx.exception))
        self.assertFalse(api.session.is_authenticated)
        self.assertEqual(len(transport.calls), 1)  # no refresh attempt on /login

    def test_bearer_header_json_and_timeout(self):
        api, transport = logged_in()
        transport.on("GET", "/orders/me", ok({"success": True, "data": [], "pagination": {}}))

        api.orders.mine()

        call = transport.calls[0]
        self.assertEqual(call.bearer, "access-1")
        self.assertEqual(call.headers["Accept"], "application/json")
        self.assertEqual(call.timeout, 10.0)
        self.assertTrue(call.base.endswith(":5004"))

    def test_public_reads_send_no_token(self):
        api, transport = logged_in()
        transport.on("GET", "/books", ok({"books": []}))
        transport.on("GET", "/authors", ok({"success": True, "data": [], "pagination": {}}))

        api.books.list()
        api.authors.list()

        self.assertEqual([c.bearer for c in transport.calls], [None, None])

    def test_protected_call_without_session(self):
        api, transport = make_api()
        with self.assertRaises(SessionExpiredError):
            api.orders.mine()
        self.assertEqual(transport.calls, [])

    def test_connection_error_is_service_unreachable(self):
        api, transport = logged_in()
        transport.down_hosts.add("http://127.0.0.1:5004")

        with self.assertRaises(ServiceUnreachableError) as ctx:
            api.orders.mine()

        self.assertEqual(friendly_message(ctx.exception), "El servicio Orders no está disponible en este momento.")
        self.assertTrue(api.session.is_authenticated)  # a network error never logs out

    def test_timeout_is_service_unreachable(self):
        api, transport = logged_in()

        def slow(_call):
            raise socket.timeout("timed out")

        transport.on("GET", "/payments/me", slow)
        with self.assertRaises(ServiceUnreachableError):
            api.payments.mine()

    def test_error_shapes_are_normalized(self):
        api, transport = logged_in(role_id=2)
        transport.on("DELETE", "/books/123", err(404, "BOOK_NOT_FOUND", "Book not found", shape="books"))
        transport.on("DELETE", "/users/9", err(409, "LAST_ADMIN_REQUIRED", "x"))
        transport.on("GET", "/orders", err(403, "FORBIDDEN", "no"))
        transport.on("GET", "/payments", err(503, "AUTH_BACKEND_UNAVAILABLE", "redis"))

        cases = [
            (lambda: api.books.delete("123"), 404, "BOOK_NOT_FOUND"),
            (lambda: api.users.delete(9), 409, "LAST_ADMIN_REQUIRED"),
            (lambda: api.orders.list_all(), 403, "FORBIDDEN"),
            (lambda: api.payments.list_all(), 503, "AUTH_BACKEND_UNAVAILABLE"),
        ]
        for action, status, code in cases:
            with self.assertRaises(ApiError) as ctx:
                action()
            self.assertEqual((ctx.exception.status, ctx.exception.code), (status, code))

    def test_error_without_json_body_uses_status(self):
        api, transport = logged_in()
        from api.http import RawResponse

        transport.on("GET", "/orders/me", RawResponse(502, b"<html>bad gateway</html>"))
        with self.assertRaises(ApiError) as ctx:
            api.orders.mine()
        self.assertEqual(ctx.exception.code, "HTTP_502")
        self.assertIn("no está disponible", friendly_message(ctx.exception))


class RefreshTests(unittest.TestCase):
    def _refresh_ok(self, access="access-2", refresh="refresh-2"):
        return ok({"success": True, "access_token": access, "refresh_token": refresh,
                   "user": {"id": 7, "email": "ana@example.com", "role_id": 1}})

    def test_expired_access_is_refreshed_and_request_retried_once(self):
        api, transport = logged_in()
        transport.on("GET", "/orders/me", lambda c: ok({"success": True, "data": ["mine"]}) if c.bearer == "access-2"
                     else err(401, "TOKEN_EXPIRED", "expired"))
        transport.on("POST", "/refresh", self._refresh_ok())

        result = api.orders.mine()

        self.assertEqual(result["data"], ["mine"])
        self.assertEqual(transport.paths(), ["GET /orders/me", "POST /refresh", "GET /orders/me"])
        refresh_call = transport.calls[1]
        self.assertEqual(refresh_call.bearer, "refresh-1")  # the REFRESH token goes to /refresh
        self.assertEqual(refresh_call.query, {"format": "json"})
        self.assertEqual((api.session.access_token, api.session.refresh_token), ("access-2", "refresh-2"))

    def test_refresh_rejected_clears_session_and_notifies(self):
        expired = []
        from fakes import make_api as _make

        api, transport = _make(on_session_expired=lambda: expired.append(True))
        api.session.start("access-1", "refresh-1", {"id": 7, "email": "e", "role_id": 1})
        transport.on("GET", "/orders/me", err(401, "TOKEN_EXPIRED", "expired"))
        transport.on("POST", "/refresh", err(401, "TOKEN_REVOKED", "revoked"))

        with self.assertRaises(SessionExpiredError):
            api.orders.mine()

        self.assertFalse(api.session.is_authenticated)
        self.assertEqual(expired, [True])
        self.assertEqual(transport.paths(), ["GET /orders/me", "POST /refresh"])

    def test_no_infinite_loop_when_new_token_is_also_rejected(self):
        api, transport = logged_in()
        transport.on("GET", "/orders/me", err(401, "TOKEN_REVOKED", "nope"))
        transport.on("POST", "/refresh", self._refresh_ok())

        with self.assertRaises(SessionExpiredError):
            api.orders.mine()

        self.assertEqual(transport.paths(), ["GET /orders/me", "POST /refresh", "GET /orders/me"])
        self.assertFalse(api.session.is_authenticated)

    def test_login_down_during_refresh_keeps_session(self):
        api, transport = logged_in()
        transport.on("GET", "/orders/me", err(401, "TOKEN_EXPIRED", "expired"))
        transport.down_hosts.add("http://127.0.0.1:5001")

        with self.assertRaises(ServiceUnreachableError):
            api.orders.mine()
        self.assertTrue(api.session.is_authenticated)  # refresh token may still be valid

    def test_403_never_triggers_refresh(self):
        api, transport = logged_in()
        transport.on("GET", "/orders", err(403, "FORBIDDEN", "no"))

        with self.assertRaises(ApiError):
            api.orders.list_all()
        self.assertEqual(transport.paths(), ["GET /orders"])

    def test_concurrent_401s_refresh_only_once(self):
        api, transport = logged_in()
        barrier = threading.Barrier(4)

        def orders(call):
            if call.bearer == "access-2":
                return ok({"success": True, "data": []})
            barrier.wait(timeout=5)  # all four requests fail with the old token together
            return err(401, "TOKEN_EXPIRED", "expired")

        transport.on("GET", "/orders/me", orders)
        transport.on("POST", "/refresh", self._refresh_ok())
        errors = []

        def worker():
            try:
                api.orders.mine()
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(transport.paths().count("POST /refresh"), 1)  # rotation-safe
        self.assertTrue(api.session.is_authenticated)


class LogoutTests(unittest.TestCase):
    def test_logout_revokes_and_clears(self):
        api, transport = logged_in()
        transport.on("POST", "/logout", ok({"success": True}))

        api.auth.logout()

        self.assertEqual(transport.calls[0].bearer, "access-1")
        self.assertFalse(api.session.is_authenticated)

    def test_logout_clears_locally_even_if_login_is_down(self):
        api, transport = logged_in()
        transport.down_hosts.add("http://127.0.0.1:5001")

        api.auth.logout()

        self.assertFalse(api.session.is_authenticated)

    def test_logout_with_expired_token_does_not_refresh(self):
        api, transport = logged_in()
        transport.on("POST", "/logout", err(401, "TOKEN_EXPIRED", "expired"))

        api.auth.logout()

        self.assertEqual(transport.paths(), ["POST /logout"])
        self.assertFalse(api.session.is_authenticated)


if __name__ == "__main__":
    unittest.main()
