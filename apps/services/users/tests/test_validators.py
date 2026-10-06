from __future__ import annotations

import pytest

from utils.errors import ServiceError
from utils.validators import parse_create, parse_patch, parse_replace


BASE = {"nombre_completo": "Ana", "email": "ana@example.com", "password": "Password123"}


def test_create_defaults_and_normalization():
    assert parse_create({**BASE, "email": " ANA@Example.com "}) == {
        "nombre_completo": "Ana",
        "email": "ana@example.com",
        "password": "Password123",
        "role_id": 1,
        "activo": True,
    }


def test_password_is_not_stripped():
    assert parse_create({**BASE, "password": " Password123 "})["password"] == " Password123 "


def test_password_72_bytes_is_accepted_73_rejected():
    assert parse_create({**BASE, "password": "a" * 72})["password"] == "a" * 72
    with pytest.raises(ServiceError):
        parse_create({**BASE, "password": "a" * 73})


def test_patch_only_returns_given_fields():
    assert parse_patch({"activo": False}) == {"activo": False}


def test_replace_keeps_password_optional():
    values = parse_replace({"nombre_completo": "A", "email": "a@example.com", "role_id": 1, "activo": True})
    assert "password" not in values


def test_server_managed_fields_are_reported_before_unknown_ones():
    with pytest.raises(ServiceError) as exc:
        parse_patch({"password_hash": "x", "foo": 1})
    assert exc.value.code == "FIELDS_NOT_ALLOWED"
