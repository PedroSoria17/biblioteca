from __future__ import annotations

import pytest

from utils.errors import ServiceError
from utils.validators import normalize_isbn, parse_create, parse_patch, parse_relation, parse_replace


def test_create_trims_and_defaults_pais():
    assert parse_create({"nombre": " A ", "apellido": " B "}) == {"nombre": "A", "apellido": "B", "pais": None}


def test_patch_only_returns_given_fields():
    assert parse_patch({"pais": None}) == {"pais": None}


def test_replace_requires_pais_key_even_if_null():
    assert parse_replace({"nombre": "A", "apellido": "B", "pais": None})["pais"] is None
    with pytest.raises(ServiceError):
        parse_replace({"nombre": "A", "apellido": "B"})


def test_relation_body_is_optional():
    assert parse_relation(None) is None
    assert parse_relation({}) is None
    assert parse_relation({"orden": 3}) == 3


def test_normalize_isbn_matches_books():
    assert normalize_isbn(" 123456789x ") == "123456789X"
    assert normalize_isbn("978-0-13-468599-1") == "978-0-13-468599-1"  # hyphens kept
