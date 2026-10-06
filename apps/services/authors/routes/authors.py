"""
/authors endpoints. JSON only (new service, no historical XML contract).

- GET: public. They never read the Authorization header nor Redis, so they
  keep working while Redis is down.
- POST/PUT/PATCH/DELETE: library_shared require_roles(ROLE_ADMIN) ->
  Bearer access token (HS256, exp, claims, type=access), revocation in
  Redis (Redis down -> 503, never "allow"), then 403 if not ADMIN.
"""

from __future__ import annotations

from flask import Blueprint, request
from library_shared.flask_auth import current_claims, require_roles
from library_shared.roles import ROLE_ADMIN

from services import author_service
from utils.errors import invalid_body
from utils.responses import ok
from utils.validators import (
    normalize_isbn,
    parse_create,
    parse_list_args,
    parse_patch,
    parse_relation,
    parse_replace,
)


authors_bp = Blueprint("authors", __name__)

# Ids outside BIGINT can never exist: the converter answers 404 for them
# without reaching PostgreSQL.
AUTHOR_ID = "<int(min=1, max=9223372036854775807):autor_id>"


def _json_body():
    # silent=True: a missing/invalid JSON body becomes None, which the
    # validators reject with a controlled 400.
    return request.get_json(silent=True)


def _optional_json_body():
    """None when there is no body at all; 400 when a body is not valid JSON."""
    if not request.get_data(cache=True):
        return None
    body = request.get_json(silent=True)
    if body is None:
        raise invalid_body()
    return body


def _actor() -> int:
    return current_claims().user_id


# ---------------------------------------------------------------------------
# Public reads
# ---------------------------------------------------------------------------

@authors_bp.get("/authors")
def list_authors():
    limit, offset, q = parse_list_args(request.args)
    authors, total = author_service.list_authors(limit, offset, q)
    return ok(authors, pagination={"limit": limit, "offset": offset, "total": total, "q": q})


@authors_bp.get(f"/authors/{AUTHOR_ID}")
def get_author(autor_id: int):
    return ok(author_service.get_author(autor_id))


@authors_bp.get(f"/authors/{AUTHOR_ID}/books")
def list_author_books(autor_id: int):
    return ok(author_service.list_author_books(autor_id))


# ---------------------------------------------------------------------------
# Author writes (ADMIN)
# ---------------------------------------------------------------------------

@authors_bp.post("/authors")
@require_roles(ROLE_ADMIN)
def create_author():
    values = parse_create(_json_body())
    return ok(author_service.create_author(values, actor_id=_actor()), status=201)


@authors_bp.put(f"/authors/{AUTHOR_ID}")
@require_roles(ROLE_ADMIN)
def replace_author(autor_id: int):
    values = parse_replace(_json_body())
    return ok(author_service.update_author(autor_id, values, actor_id=_actor()))


@authors_bp.patch(f"/authors/{AUTHOR_ID}")
@require_roles(ROLE_ADMIN)
def patch_author(autor_id: int):
    values = parse_patch(_json_body())
    return ok(author_service.update_author(autor_id, values, actor_id=_actor()))


@authors_bp.delete(f"/authors/{AUTHOR_ID}")
@require_roles(ROLE_ADMIN)
def delete_author(autor_id: int):
    author_service.delete_author(autor_id, actor_id=_actor())
    return ok({"autor_id": autor_id, "deleted": True})


# ---------------------------------------------------------------------------
# Author <-> book relations (ADMIN). The relation is a sub-resource of the
# author: the books of /authors/<id>/books are exactly these rows.
# ---------------------------------------------------------------------------

@authors_bp.post(f"/authors/{AUTHOR_ID}/books/<isbn>")
@require_roles(ROLE_ADMIN)
def add_book(autor_id: int, isbn: str):
    orden = parse_relation(_optional_json_body())
    relation = author_service.add_book(autor_id, normalize_isbn(isbn), orden, actor_id=_actor())
    return ok(relation, status=201)


@authors_bp.delete(f"/authors/{AUTHOR_ID}/books/<isbn>")
@require_roles(ROLE_ADMIN)
def remove_book(autor_id: int, isbn: str):
    normalized = normalize_isbn(isbn)
    author_service.remove_book(autor_id, normalized, actor_id=_actor())
    return ok({"autor_id": autor_id, "isbn": normalized, "deleted": True})
