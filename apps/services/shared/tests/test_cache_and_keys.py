import pytest
from flask import Flask

from library_shared import keys
from library_shared.cache import cached_json
from library_shared.cors import init_cors
from library_shared.settings import CorsSettings


def test_key_conventions():
    assert keys.revoked_jwt_key("abc") == "jwt:revoked:abc"
    assert keys.book_key("9780306406157") == "books:9780306406157"
    assert keys.refresh_token_key("j") == "auth:refresh:j"
    assert keys.session_key("s") == "auth:session:s"
    with pytest.raises(ValueError):
        keys.revoked_jwt_key(" ")


def test_books_list_key_is_normalized():
    a = keys.books_list_key({"Titulo": " Dune ", "page": 1, "empty": "", "none": None})
    b = keys.books_list_key({"page": "1", "titulo": "Dune"})

    assert a == b == "books:list:page=1&titulo=Dune"
    assert keys.books_list_key() == "books:list:all"
    assert keys.books_list_key({"titulo": "a&b=c"}) == "books:list:titulo=a%26b%3Dc"


def test_cached_json_reads_through_and_then_hits_cache(gateway):
    calls = []

    def loader():
        calls.append(1)
        return [{"isbn": "1"}]

    assert cached_json(gateway, "books:list:all", 30, loader) == [{"isbn": "1"}]
    assert cached_json(gateway, "books:list:all", 30, loader) == [{"isbn": "1"}]
    assert len(calls) == 1


def test_cached_json_falls_back_to_loader_when_redis_is_down(broken_gateway):
    # Redis is only an optimization: PostgreSQL (the loader) still answers.
    assert cached_json(broken_gateway, "books:list:all", 30, lambda: ["from-db"]) == ["from-db"]


def test_cached_json_without_gateway(gateway):
    assert cached_json(None, "k", 30, lambda: {"a": 1}) == {"a": 1}


def test_cached_json_discards_corrupt_entry(gateway, fake_redis):
    fake_redis.set("books:1", "{not json", ex=30)

    assert cached_json(gateway, "books:1", 30, lambda: {"isbn": "1"}) == {"isbn": "1"}
    assert fake_redis.get("books:1") == '{"isbn": "1"}'


def _cors_client(origins):
    app = Flask(__name__)
    init_cors(app, CorsSettings(allowed_origins=origins))

    @app.get("/books")
    def books():
        return {"ok": True}

    return app.test_client()


def test_cors_allows_only_configured_origin():
    client = _cors_client(("http://localhost:3000",))

    allowed = client.get("/books", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/books", headers={"Origin": "http://evil.example"})

    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_cors_disabled_when_no_origins():
    resp = _cors_client(()).get("/books", headers={"Origin": "http://localhost:3000"})

    assert "Access-Control-Allow-Origin" not in resp.headers
