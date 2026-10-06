"""POST/DELETE /authors/<autor_id>/books/<isbn> (rows of libro_autor)."""

from __future__ import annotations

import copy

import pytest

from conftest import BORGES, CORTAZAR, ISBN_ALEPH, ISBN_FICCIONES, ISBN_HUERFANO, ISBN_RAYUELA, SIN_LIBROS


def test_create_relation_returns_201(client, admin_headers, author_db):
    response = client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_HUERFANO}", headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"] == {
        "autor_id": SIN_LIBROS,
        "isbn": ISBN_HUERFANO,
        "titulo": "Libro sin autores",
        "anio_publicacion": 2001,
        "orden": 1,
    }
    assert author_db.relations[(ISBN_HUERFANO, SIN_LIBROS)] == 1


def test_new_coauthor_is_appended_after_existing_authors(client, admin_headers, author_db):
    response = client.post(f"/authors/{BORGES}/books/{ISBN_RAYUELA}", headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["orden"] == 2
    assert author_db.relations[(ISBN_RAYUELA, CORTAZAR)] == 1  # untouched


def test_explicit_orden_is_used(client, admin_headers, author_db):
    response = client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_RAYUELA}", json={"orden": 5}, headers=admin_headers)

    assert response.status_code == 201
    assert author_db.relations[(ISBN_RAYUELA, SIN_LIBROS)] == 5


@pytest.mark.parametrize("body", [{"orden": 0}, {"orden": -1}, {"orden": "2"}, {"orden": True}, {"orden": 40000}])
def test_invalid_orden_returns_400(client, admin_headers, author_db, body):
    response = client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_RAYUELA}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert (ISBN_RAYUELA, SIN_LIBROS) not in author_db.relations


@pytest.mark.parametrize("body,code", [({"foo": 1}, "UNKNOWN_FIELDS"), ({"isbn": "x"}, "FIELDS_NOT_ALLOWED")])
def test_relation_body_unknown_or_managed_fields_return_400(client, admin_headers, body, code):
    response = client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_RAYUELA}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == code


def test_relation_with_malformed_json_body_returns_400(client, admin_headers):
    response = client.post(
        f"/authors/{SIN_LIBROS}/books/{ISBN_RAYUELA}",
        data="{orden:",
        content_type="application/json",
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_isbn_is_normalized_like_books(client, admin_headers, author_db):
    author_db.add_book("123456789X", "ISBN-10 con X")

    response = client.post(f"/authors/{SIN_LIBROS}/books/%20123456789x%20", headers=admin_headers)

    assert response.status_code == 201
    assert ("123456789X", SIN_LIBROS) in author_db.relations


def test_relation_with_unknown_author_returns_404(client, admin_headers, author_db):
    response = client.post(f"/authors/999/books/{ISBN_HUERFANO}", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"


@pytest.mark.parametrize("isbn", ["9789999999999", "x" * 21])
def test_relation_with_unknown_book_returns_404(client, admin_headers, author_db, isbn):
    before = dict(author_db.relations)

    response = client.post(f"/authors/{SIN_LIBROS}/books/{isbn}", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "BOOK_NOT_FOUND"
    assert author_db.relations == before


def test_duplicate_relation_returns_409(client, admin_headers, author_db):
    response = client.post(f"/authors/{BORGES}/books/{ISBN_FICCIONES}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "RELATION_ALREADY_EXISTS"
    assert author_db.relations[(ISBN_FICCIONES, BORGES)] == 1


def test_duplicate_relation_race_is_409_not_500(client, admin_headers, monkeypatch):
    from repositories import author_repository

    monkeypatch.setattr(author_repository, "relation_exists", lambda *_a, **_k: False)

    response = client.post(f"/authors/{BORGES}/books/{ISBN_FICCIONES}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "RELATION_ALREADY_EXISTS"  # libro_autor_pkey


def test_book_deleted_concurrently_is_404_not_500(client, admin_headers, author_db, monkeypatch):
    from repositories import author_repository

    # Books deletes the book between our check and the INSERT.
    real_get_book = author_db.get_book

    def get_then_vanish(conn, isbn):
        book = real_get_book(conn, isbn)
        author_db.books.pop(isbn, None)
        return book

    monkeypatch.setattr(author_repository, "get_book", get_then_vanish)

    response = client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_HUERFANO}", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "BOOK_NOT_FOUND"  # libro_autor_isbn_fkey


def test_delete_relation_removes_only_the_relation(client, admin_headers, author_db):
    authors_before = copy.deepcopy(author_db.authors)
    books_before = copy.deepcopy(author_db.books)

    response = client.delete(f"/authors/{BORGES}/books/{ISBN_ALEPH}", headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json()["data"] == {"autor_id": BORGES, "isbn": ISBN_ALEPH, "deleted": True}
    assert (ISBN_ALEPH, BORGES) not in author_db.relations
    assert (ISBN_FICCIONES, BORGES) in author_db.relations
    assert author_db.authors == authors_before
    assert author_db.books == books_before


def test_delete_last_author_of_a_book_keeps_the_book(client, admin_headers, author_db):
    response = client.delete(f"/authors/{CORTAZAR}/books/{ISBN_RAYUELA}", headers=admin_headers)

    assert response.status_code == 200
    assert ISBN_RAYUELA in author_db.books
    assert CORTAZAR in author_db.authors


def test_delete_nonexistent_relation_returns_404(client, admin_headers):
    response = client.delete(f"/authors/{CORTAZAR}/books/{ISBN_FICCIONES}", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "RELATION_NOT_FOUND"


def test_delete_relation_of_unknown_author_or_book_returns_404(client, admin_headers):
    assert client.delete(f"/authors/999/books/{ISBN_FICCIONES}", headers=admin_headers).get_json()["code"] == (
        "AUTHOR_NOT_FOUND"
    )
    assert client.delete(f"/authors/{BORGES}/books/9789999999999", headers=admin_headers).get_json()["code"] == (
        "BOOK_NOT_FOUND"
    )


def test_relations_are_reflected_in_author_books(client, admin_headers):
    client.post(f"/authors/{SIN_LIBROS}/books/{ISBN_HUERFANO}", headers=admin_headers)

    books = client.get(f"/authors/{SIN_LIBROS}/books").get_json()["data"]["books"]

    assert [b["isbn"] for b in books] == [ISBN_HUERFANO]
