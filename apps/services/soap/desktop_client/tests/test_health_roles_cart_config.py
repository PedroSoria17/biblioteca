from __future__ import annotations

import time
import unittest

from api.health import DEGRADED, DOWN, UP
from api.http import RawResponse
from cart import Cart, parse_quantity
from client_config import ConfigError, load_config, read_env_file
from fakes import make_api, ok
from permissions import ADMIN_TABS, USER_TABS, can, tabs_for


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.api, self.transport = make_api()

    def test_states(self):
        self.transport.on("GET", "/health", lambda call: {
            ":5000": ok({"status": "degraded", "database": "connected", "redis": "unavailable"}),
            ":5001": ok({"status": "healthy", "database": "connected", "redis": "connected"}),
            ":5002": ok({"status": "unhealthy", "redis": "unavailable"}, 503),
            ":5003": ok({"status": "degraded"}),
            ":5004": ok({"status": "unavailable", "database": "unavailable"}, 503),
            ":5005": RawResponse(200, b""),
        }[call.base[-5:]])

        result = {h.service: h.state for h in self.api.health.check_all(["books", "login", "users", "authors", "orders", "payments"])}

        self.assertEqual(result, {"books": DEGRADED, "login": UP, "users": DOWN, "authors": DEGRADED,
                                  "orders": DOWN, "payments": UP})

    def test_books_is_checked_with_details(self):
        self.transport.on("GET", "/health", ok({"status": "ok"}))
        self.api.health.check("books")
        self.assertEqual(self.transport.calls[0].query, {"details": "true", "format": "json"})

    def test_offline_service_is_down_and_never_raises(self):
        self.transport.down_hosts.add("http://127.0.0.1:5005")
        health = self.api.health.check("payments")
        self.assertEqual((health.state, health.detail), (DOWN, "sin respuesta"))

    def test_checks_run_in_parallel_with_short_timeout(self):
        def slow(call):
            time.sleep(0.3)
            return ok({"status": "healthy"})

        self.transport.on("GET", "/health", slow)
        started = time.monotonic()
        self.api.health.check_all(["books", "login", "users", "authors", "orders", "payments"])
        self.assertLess(time.monotonic() - started, 1.2)
        self.assertTrue(all(c.timeout == 3.0 for c in self.transport.calls))


class RoleTests(unittest.TestCase):
    def test_user_gets_no_admin_tabs_or_actions(self):
        self.assertEqual(tabs_for(1), USER_TABS)
        for tab in ("users", "all_orders", "all_payments"):
            self.assertNotIn(tab, tabs_for(1))
        for action in ("books.create", "users.delete", "payments.approve", "payments.refund", "orders.cancel", "authors.link"):
            self.assertFalse(can(1, action), action)
        for action in ("orders.create", "payments.create", "cart.use", "orders.mine"):
            self.assertTrue(can(1, action), action)

    def test_admin_gets_everything(self):
        self.assertEqual(tabs_for(2), ADMIN_TABS)
        for action in ("books.create", "users.delete", "payments.approve", "payments.refund", "orders.cancel", "orders.create"):
            self.assertTrue(can(2, action), action)

    def test_anonymous_gets_nothing(self):
        self.assertEqual(tabs_for(None), ())
        self.assertFalse(can(None, "orders.mine"))


class CartTests(unittest.TestCase):
    def test_consolidates_same_isbn_and_builds_order_body(self):
        cart = Cart()
        cart.add("9780000000002", "B", 1)
        cart.add(" 9780000000001 ", "A", 2)
        cart.add("9780000000001", "A", 3)

        self.assertEqual(cart.to_order_items(), [{"isbn": "9780000000001", "cantidad": 5}, {"isbn": "9780000000002", "cantidad": 1}])
        cart.remove("9780000000002")
        self.assertEqual(len(cart.lines), 1)
        cart.clear()
        self.assertTrue(cart.is_empty())

    def test_quantity_validation_is_ux_only(self):
        for bad in ("0", "-1", "1.5", "abc", ""):
            with self.assertRaises(ValueError):
                parse_quantity(bad)
        self.assertEqual(parse_quantity(" 3 "), 3)
        with self.assertRaises(ValueError):
            Cart().add("1", "t", True)


class ConfigTests(unittest.TestCase):
    def test_defaults_are_local(self):
        config = load_config(env={}, env_file=None)
        self.assertEqual(config.url("books"), "http://127.0.0.1:5000")
        self.assertEqual(config.url("payments"), "http://127.0.0.1:5005")
        self.assertEqual(config.soap_endpoint, "http://127.0.0.1:5000/soap")

    def test_environment_overrides_and_trailing_slash(self):
        config = load_config(env={"ORDERS_BASE_URL": "https://library.example.com/orders/", "HTTP_TIMEOUT_SECONDS": "5"}, env_file=None)
        self.assertEqual(config.url("orders"), "https://library.example.com/orders")
        self.assertEqual(config.http_timeout, 5.0)

    def test_env_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# comment\nUSERS_BASE_URL=http://10.0.0.5:5002\n\nJUNK\n", encoding="utf-8")
            self.assertEqual(read_env_file(path), {"USERS_BASE_URL": "http://10.0.0.5:5002"})
            self.assertEqual(load_config(env={}, env_file=path).url("users"), "http://10.0.0.5:5002")

    def test_invalid_values(self):
        with self.assertRaises(ConfigError):
            load_config(env={"BOOKS_BASE_URL": "127.0.0.1:5000"}, env_file=None)
        with self.assertRaises(ConfigError):
            load_config(env={"HTTP_TIMEOUT_SECONDS": "0"}, env_file=None)


if __name__ == "__main__":
    unittest.main()
