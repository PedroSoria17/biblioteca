"""
What each role sees in the desktop client. This only shapes the UI: the
backend still enforces every permission (a USER clicking a hidden action
would get 403 anyway).
"""

from __future__ import annotations

from api.session import ROLE_ADMIN, ROLE_USER


# Tabs, in display order.
USER_TABS = ("catalog", "authors", "my_orders", "my_payments", "classifier")
ADMIN_TABS = ("catalog", "authors", "my_orders", "my_payments", "users", "all_orders", "all_payments", "classifier")

ADMIN_ACTIONS = frozenset(
    {
        "books.create", "books.edit", "books.delete",
        "authors.create", "authors.edit", "authors.delete", "authors.link", "authors.unlink",
        "users.list", "users.create", "users.edit", "users.delete", "users.password", "users.toggle",
        "orders.list_all", "orders.cancel", "orders.complete",
        "payments.list_all", "payments.approve", "payments.reject", "payments.refund",
    }
)

USER_ACTIONS = frozenset(
    {
        "books.read", "authors.read", "cart.use",
        "orders.create", "orders.mine", "orders.items",
        "payments.create", "payments.mine",
    }
)


def tabs_for(role_id: int | None) -> tuple[str, ...]:
    if role_id == ROLE_ADMIN:
        return ADMIN_TABS
    if role_id == ROLE_USER:
        return USER_TABS
    return ()


def can(role_id: int | None, action: str) -> bool:
    if role_id == ROLE_ADMIN:
        return action in ADMIN_ACTIONS or action in USER_ACTIONS
    if role_id == ROLE_USER:
        return action in USER_ACTIONS
    return False
