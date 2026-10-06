"""
/users endpoints. JSON only (new service, no historical XML contract).

Authentication/authorization is entirely library_shared:
- require_auth: Bearer access token (HS256, exp, claims, type=access) and
  revocation check in Redis (Redis down -> 503, never "allow").
- require_roles(ROLE_ADMIN): same as above, then 403 if role_id != ADMIN.
"""

from __future__ import annotations

from flask import Blueprint, request
from library_shared.flask_auth import current_claims, require_auth, require_roles
from library_shared.roles import ROLE_ADMIN

from services import user_service
from utils.responses import ok
from utils.validators import parse_create, parse_pagination, parse_patch, parse_replace


users_bp = Blueprint("users", __name__)


def _json_body():
    # silent=True: a missing/invalid JSON body becomes None, which the
    # validators reject with a controlled 400.
    return request.get_json(silent=True)


@users_bp.get("/users")
@require_roles(ROLE_ADMIN)
def list_users():
    limit, offset = parse_pagination(request.args)
    users, total = user_service.list_users(limit, offset)
    return ok(users, pagination={"limit": limit, "offset": offset, "total": total})


# Registered before /users/<int:...>; "me" never matches the int converter
# anyway, so there is no ambiguity between both routes.
@users_bp.get("/users/me")
@require_auth
def get_me():
    # The id comes ONLY from the validated token, never from the request.
    return ok(user_service.get_user(current_claims().user_id))


@users_bp.get("/users/<int:usuario_id>")
@require_roles(ROLE_ADMIN)
def get_user(usuario_id: int):
    return ok(user_service.get_user(usuario_id))


@users_bp.post("/users")
@require_roles(ROLE_ADMIN)
def create_user():
    values = parse_create(_json_body())
    return ok(user_service.create_user(values, actor_id=current_claims().user_id), status=201)


@users_bp.put("/users/<int:usuario_id>")
@require_roles(ROLE_ADMIN)
def replace_user(usuario_id: int):
    values = parse_replace(_json_body())
    return ok(user_service.update_user(usuario_id, values, actor_id=current_claims().user_id))


@users_bp.patch("/users/<int:usuario_id>")
@require_roles(ROLE_ADMIN)
def patch_user(usuario_id: int):
    values = parse_patch(_json_body())
    return ok(user_service.update_user(usuario_id, values, actor_id=current_claims().user_id))


@users_bp.delete("/users/<int:usuario_id>")
@require_roles(ROLE_ADMIN)
def delete_user(usuario_id: int):
    user_service.delete_user(usuario_id, actor_id=current_claims().user_id)
    return ok({"usuario_id": usuario_id, "deleted": True})
