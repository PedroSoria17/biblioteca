"""
Payments endpoints. JSON only. Everything except /health requires a valid
access token (library_shared; Redis down -> 503). The owner of a payment is
pedidos.usuario_id, compared with claims.user_id; it is never taken from
the request.

Payments are financial history: there is no PUT/PATCH/DELETE (Flask
answers 405). State changes only happen through approve / reject / refund.
"""

from __future__ import annotations

from flask import Blueprint, request
from library_shared.flask_auth import current_claims, require_auth, require_roles
from library_shared.roles import ROLE_ADMIN

from services import payment_service
from utils.responses import ok
from utils.validators import parse_create_payment, parse_empty_body, parse_filters, parse_pagination


payments_bp = Blueprint("payments", __name__)

PAGO_ID = "<int(min=1, max=9223372036854775807):pago_id>"
PEDIDO_ID = "<int(min=1, max=9223372036854775807):pedido_id>"


def _caller() -> tuple[int, bool]:
    claims = current_claims()
    return claims.user_id, claims.role_id == ROLE_ADMIN


def _no_body() -> None:
    has_data = bool(request.get_data(cache=True))
    parse_empty_body(request.get_json(silent=True) if has_data else None, has_data)


def _list(filters):
    limit, offset = parse_pagination(request.args)
    payments, total = payment_service.list_payments(filters, limit, offset)
    return ok(payments, pagination={"limit": limit, "offset": offset, "total": total})


@payments_bp.get("/payments")
@require_roles(ROLE_ADMIN)
def list_payments():
    return _list(parse_filters(request.args))


@payments_bp.get("/payments/me")
@require_auth
def list_my_payments():
    filters = parse_filters(request.args)
    filters["usuario_id"] = current_claims().user_id
    return _list(filters)


@payments_bp.get(f"/payments/{PAGO_ID}")
@require_auth
def get_payment(pago_id: int):
    user_id, is_admin = _caller()
    return ok(payment_service.get_payment(pago_id, user_id, is_admin))


@payments_bp.get(f"/orders/{PEDIDO_ID}/payments")
@require_auth
def list_order_payments(pedido_id: int):
    user_id, is_admin = _caller()
    return ok(payment_service.list_order_payments(pedido_id, user_id, is_admin))


@payments_bp.post("/payments")
@require_auth
def create_payment():
    values = parse_create_payment(request.get_json(silent=True))
    user_id, is_admin = _caller()
    return ok(payment_service.create_payment(values, user_id, is_admin), status=201)


@payments_bp.post(f"/payments/{PAGO_ID}/approve")
@require_roles(ROLE_ADMIN)
def approve_payment(pago_id: int):
    _no_body()
    return ok(payment_service.approve_payment(pago_id, actor_id=current_claims().user_id))


@payments_bp.post(f"/payments/{PAGO_ID}/reject")
@require_roles(ROLE_ADMIN)
def reject_payment(pago_id: int):
    _no_body()
    return ok(payment_service.reject_payment(pago_id, actor_id=current_claims().user_id))


@payments_bp.post(f"/payments/{PAGO_ID}/refund")
@require_roles(ROLE_ADMIN)
def refund_payment(pago_id: int):
    _no_body()
    return ok(payment_service.refund_payment(pago_id, actor_id=current_claims().user_id))
