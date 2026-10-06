from __future__ import annotations

import copy

import pytest

from conftest import BORGES, CORTAZAR, ISBN_FICCIONES, ISBN_RAYUELA, SIN_LIBROS


VALID = {"nombre": "  Gabriel  ", "apellido": " García Márquez ", "pais": " Colombia "}


# ---------------------------------------------------------------------------
# POST /authors
# ---------------------------------------------------------------------------

def test_create_author_returns_201(client, admin_headers, author_db):
    response = client.post("/authors", json=VALID, headers=admin_headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data == {
        "autor_id": 4,
        "nombre": "Gabriel",
        "apellido": "García Márquez",
        "pais": "Colombia",
        "books_count": 0,
    }
    assert author_db.authors[4]["apellido"] == "García Márquez"


def test_create_author_without_pais_stores_null(client, admin_headers, author_db):
    response = client.post("/authors", json={"nombre": "Anónimo", "apellido": "Desconocido"}, headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["pais"] is None


def test_create_homonym_is_allowed_because_the_table_has_no_unique(client, admin_headers, author_db):
    body = {"nombre": "Jorge Luis", "apellido": "Borges", "pais": "Argentina"}

    response = client.post("/authors", json=body, headers=admin_headers)

    assert response.status_code == 201
    assert len(author_db.authors) == 4


@pytest.mark.parametrize("missing", ["nombre", "apellido"])
def test_create_missing_required_field_returns_400(client, admin_headers, missing):
    body = {k: v for k, v in VALID.items() if k != missing}

    response = client.post("/authors", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert missing in response.get_json()["message"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("nombre", ""),
        ("nombre", "   "),
        ("nombre", None),
        ("nombre", 5),
        ("nombre", "x" * 121),
        ("apellido", ""),
        ("apellido", None),
        ("apellido", ["Borges"]),
        ("apellido", "x" * 121),
        ("pais", ""),
        ("pais", "   "),
        ("pais", 1),
        ("pais", "x" * 81),
    ],
)
def test_create_invalid_values_return_400(client, admin_headers, author_db, field, value):
    response = client.post("/authors", json={**VALID, field: value}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"
    assert len(author_db.authors) == 3


def test_create_max_lengths_are_accepted(client, admin_headers):
    body = {"nombre": "n" * 120, "apellido": "a" * 120, "pais": "p" * 80}

    assert client.post("/authors", json=body, headers=admin_headers).status_code == 201


def test_create_unknown_fields_returns_400(client, admin_headers):
    response = client.post("/authors", json={**VALID, "nacionalidad": "x", "edad": 3}, headers=admin_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "UNKNOWN_FIELDS"
    assert body["details"] == {"fields": ["edad", "nacionalidad"]}


def test_create_with_autor_id_returns_400(client, admin_headers):
    response = client.post("/authors", json={**VALID, "autor_id": 99}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "not json", "content_type": "application/json"},
        {"data": "nombre=x", "content_type": "application/x-www-form-urlencoded"},
        {"json": ["a", "list"]},
        {},
    ],
)
def test_create_with_non_object_body_returns_400(client, admin_headers, kwargs):
    response = client.post("/authors", headers=admin_headers, **kwargs)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# PUT /authors/<id>
# ---------------------------------------------------------------------------

def test_put_replaces_all_fields(client, admin_headers, author_db):
    body = {"nombre": "Jorge Francisco Isidoro Luis", "apellido": "Borges Acevedo", "pais": None}

    response = client.put(f"/authors/{BORGES}", json=body, headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json()["data"] == {"autor_id": BORGES, **body, "books_count": 2}
    assert author_db.authors[BORGES]["pais"] is None


@pytest.mark.parametrize("missing", ["nombre", "apellido", "pais"])
def test_put_requires_every_field(client, admin_headers, missing):
    body = {"nombre": "N", "apellido": "A", "pais": "P"}
    body.pop(missing)

    response = client.put(f"/authors/{BORGES}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert missing in response.get_json()["message"]


def test_put_unknown_author_returns_404(client, admin_headers):
    response = client.put("/authors/999", json={"nombre": "N", "apellido": "A", "pais": None}, headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"


def test_put_with_user_returns_403(client, user_headers):
    response = client.put(f"/authors/{BORGES}", json={"nombre": "N", "apellido": "A", "pais": None}, headers=user_headers)

    assert response.status_code == 403


def test_put_cannot_change_id(client, admin_headers):
    body = {"autor_id": 50, "nombre": "N", "apellido": "A", "pais": None}

    response = client.put(f"/authors/{BORGES}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# PATCH /authors/<id>
# ---------------------------------------------------------------------------

def test_patch_only_changes_given_field(client, admin_headers, author_db):
    before = dict(author_db.authors[CORTAZAR])

    response = client.patch(f"/authors/{CORTAZAR}", json={"nombre": "Julio Florencio"}, headers=admin_headers)

    assert response.status_code == 200
    after = author_db.authors[CORTAZAR]
    assert after["nombre"] == "Julio Florencio"
    assert after["apellido"] == before["apellido"]
    assert after["pais"] == before["pais"]


def test_patch_pais_null_clears_it(client, admin_headers, author_db):
    response = client.patch(f"/authors/{CORTAZAR}", json={"pais": None}, headers=admin_headers)

    assert response.status_code == 200
    assert author_db.authors[CORTAZAR]["pais"] is None
    assert author_db.authors[CORTAZAR]["nombre"] == "Julio"


def test_patch_does_not_touch_relations_or_books(client, admin_headers, author_db):
    before = copy.deepcopy((author_db.books, author_db.relations))

    client.patch(f"/authors/{BORGES}", json={"apellido": "Borges A."}, headers=admin_headers)

    assert (author_db.books, author_db.relations) == before


def test_patch_unknown_author_returns_404(client, admin_headers):
    response = client.patch("/authors/999", json={"nombre": "N"}, headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"


@pytest.mark.parametrize("body", [{}, {"nombre": None}, {"apellido": ""}, {"foo": 1}])
def test_patch_invalid_body_returns_400(client, admin_headers, author_db, body):
    before = copy.deepcopy(author_db.authors)

    response = client.patch(f"/authors/{BORGES}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert author_db.authors == before


# ---------------------------------------------------------------------------
# DELETE /authors/<id>
# ---------------------------------------------------------------------------

def test_delete_author_without_books(client, admin_headers, author_db):
    books_before = copy.deepcopy(author_db.books)
    relations_before = dict(author_db.relations)

    response = client.delete(f"/authors/{SIN_LIBROS}", headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"autor_id": SIN_LIBROS, "deleted": True}}
    assert SIN_LIBROS not in author_db.authors
    assert author_db.books == books_before
    assert author_db.relations == relations_before


def test_delete_author_with_books_returns_409_and_deletes_nothing(client, admin_headers, author_db):
    before = copy.deepcopy((author_db.authors, author_db.books, author_db.relations))

    response = client.delete(f"/authors/{BORGES}", headers=admin_headers)

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "AUTHOR_HAS_BOOKS"
    assert body["details"] == {"books_count": 2}
    assert (author_db.authors, author_db.books, author_db.relations) == before


def test_delete_after_removing_relations_never_deletes_the_books(client, admin_headers, author_db):
    assert client.delete(f"/authors/{CORTAZAR}/books/{ISBN_RAYUELA}", headers=admin_headers).status_code == 200

    response = client.delete(f"/authors/{CORTAZAR}", headers=admin_headers)

    assert response.status_code == 200
    assert CORTAZAR not in author_db.authors
    assert ISBN_RAYUELA in author_db.books


def test_delete_unknown_author_returns_404(client, admin_headers):
    response = client.delete("/authors/999", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"


def test_delete_fk_restrict_race_is_409_not_500(client, admin_headers, author_db, monkeypatch):
    from repositories import author_repository

    # A relation is created between the explicit check and the DELETE:
    # libro_autor_autor_id_fkey (RESTRICT) rejects it.
    real_get = author_db.get_author
    monkeypatch.setattr(
        author_repository, "get_author", lambda conn, autor_id, for_update=False: {**real_get(conn, autor_id), "books_count": 0}
    )

    response = client.delete(f"/authors/{BORGES}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "AUTHOR_HAS_BOOKS"
    assert BORGES in author_db.authors
    assert (ISBN_FICCIONES, BORGES) in author_db.relations
