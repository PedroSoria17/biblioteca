"""Public GETs: no JWT, and they keep working while Redis is down."""

from __future__ import annotations

import pytest

from conftest import BORGES, CORTAZAR, ISBN_ALEPH, ISBN_FICCIONES, SIN_LIBROS, bearer


def test_list_authors_without_token(client):
    response = client.get("/authors")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    # Ordered by apellido, nombre.
    assert [a["apellido"] for a in body["data"]] == ["Borges", "Cortázar", "Sin Libros"]
    assert body["pagination"] == {"limit": 50, "offset": 0, "total": 3, "q": None}
    assert body["data"][0] == {
        "autor_id": BORGES,
        "nombre": "Jorge Luis",
        "apellido": "Borges",
        "pais": "Argentina",
        "books_count": 2,
    }


def test_list_authors_pagination(client):
    body = client.get("/authors?limit=1&offset=1").get_json()

    assert [a["autor_id"] for a in body["data"]] == [CORTAZAR]
    assert body["pagination"]["total"] == 3


@pytest.mark.parametrize(
    "q,expected",
    [
        ("borges", [BORGES]),
        ("JULIO", [CORTAZAR]),
        ("Luis Borges", [BORGES]),  # nombre + apellido
        ("argentina", [BORGES, CORTAZAR]),  # pais
        ("nadie", []),
    ],
)
def test_list_authors_search(client, q, expected):
    body = client.get(f"/authors?q={q}").get_json()

    assert [a["autor_id"] for a in body["data"]] == expected
    assert body["pagination"]["total"] == len(expected)
    assert body["pagination"]["q"] == q


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=x", "offset=-1", "q=" + "a" * 121])
def test_list_authors_invalid_query_returns_400(client, query):
    response = client.get(f"/authors?{query}")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


def test_get_existing_author(client):
    response = client.get(f"/authors/{SIN_LIBROS}")

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "autor_id": SIN_LIBROS,
        "nombre": "Ana",
        "apellido": "Sin Libros",
        "pais": None,
        "books_count": 0,
    }


@pytest.mark.parametrize("path", ["/authors/999", "/authors/0", "/authors/abc", "/authors/99999999999999999999"])
def test_get_unknown_author_returns_404(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.is_json


def test_get_unknown_author_code(client):
    assert client.get("/authors/999").get_json() == {
        "success": False,
        "code": "AUTHOR_NOT_FOUND",
        "message": "Author not found.",
    }


def test_get_author_books(client):
    response = client.get(f"/authors/{BORGES}/books")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["author"]["autor_id"] == BORGES
    assert data["books"] == [
        {"isbn": ISBN_ALEPH, "titulo": "El Aleph", "anio_publicacion": 1949, "orden": 1},
        {"isbn": ISBN_FICCIONES, "titulo": "Ficciones", "anio_publicacion": 1944, "orden": 1},
    ]


def test_get_books_of_author_without_books(client):
    assert client.get(f"/authors/{SIN_LIBROS}/books").get_json()["data"]["books"] == []


def test_get_books_of_unknown_author_returns_404(client):
    response = client.get("/authors/999/books")

    assert response.status_code == 404
    assert response.get_json()["code"] == "AUTHOR_NOT_FOUND"


@pytest.mark.parametrize("path", ["/authors", f"/authors/{BORGES}", f"/authors/{BORGES}/books", "/authors?q=bor"])
def test_public_reads_work_with_redis_down_and_never_touch_redis(client, fake_redis, path):
    fake_redis.down = True
    calls_before = fake_redis.calls

    response = client.get(path)

    assert response.status_code == 200
    assert fake_redis.calls == calls_before


def test_public_reads_ignore_an_invalid_authorization_header(client):
    # Reads are public: a broken/expired token sent by a client is not
    # evaluated (it neither grants nor denies anything here).
    response = client.get("/authors", headers=bearer("not-a-jwt"))

    assert response.status_code == 200


def test_database_down_returns_503_without_leaking_details(client, author_db):
    author_db.down = True

    response = client.get("/authors")

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"
    assert "db-test-password" not in response.get_data(as_text=True)


def test_unknown_route_and_wrong_method_are_json(client):
    assert client.get("/nope").is_json
    response = client.post(f"/authors/{BORGES}/books")
    assert response.status_code == 405
    assert response.is_json
