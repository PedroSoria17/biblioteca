"""
/orders endpoints. JSON only. Every endpoint requires a valid access token
(library_shared: HS256, exp, claims, type=access, revocation in Redis;
Redis down -> 503). The owner of an order ALWAYS comes from the token.

Orders does not physically delete orders; cancellation is represented by
status. There is intentionally no DELETE route (Flask answers 405).
"""

from __future__ import annotations

from flask import Blueprint, request
from library_shared.flask_auth import current_claims, require_auth, require_roles
from library_shared.roles import ROLE_ADMIN

from services import order_service
from utils.responses import ok
from utils.validators import (
    parse_admin_filters,
    parse_create_order,
    parse_own_filters,
    parse_pagination,
    parse_status,
)


orders_bp = Blueprint("orders", __name__)

ORDER_ID = "<int(min=1, max=9223372036854775807):pedido_id>"


def _json_body():
    return request.get_json(silent=True)


def _caller() -> tuple[int, bool]:
    claims = current_claims()
    return claims.user_id, claims.role_id == ROLE_ADMIN


def _list(filters):
    limit, offset = parse_pagination(request.args)
    orders, total = order_service.list_orders(filters, limit, offset)
    return ok(orders, pagination={"limit": limit, "offset": offset, "total": total})


@orders_bp.get("/orders")
@require_roles(ROLE_ADMIN)
def list_orders():
    return _list(parse_admin_filters(request.args))


@orders_bp.get("/orders/me")
@require_auth
def list_my_orders():
    filters = parse_own_filters(request.args)
    filters["usuario_id"] = current_claims().user_id
    return _list(filters)


@orders_bp.get(f"/orders/{ORDER_ID}")
@require_auth
def get_order(pedido_id: int):
    user_id, is_admin = _caller()
    return ok(order_service.get_order(pedido_id, user_id, is_admin))


@orders_bp.get(f"/orders/{ORDER_ID}/items")
@require_auth
def get_items(pedido_id: int):
    user_id, is_admin = _caller()
    return ok(order_service.get_items(pedido_id, user_id, is_admin))


@orders_bp.post("/orders")
@require_auth
def create_order():
    # Any authenticated user (ADMIN included) buys for ITSELF.
    lines = parse_create_order(_json_body())
    return ok(order_service.create_order(current_claims().user_id, lines), status=201)


@orders_bp.patch(f"/orders/{ORDER_ID}/status")
@require_roles(ROLE_ADMIN)
def change_status(pedido_id: int):
    estado = parse_status(_json_body())
    return ok(order_service.change_status(pedido_id, estado, actor_id=current_claims().user_id))
