from utils.validators import (
    is_valid_email,
    is_valid_password,
    normalize_email,
    normalize_text,
)


def test_normalize_text_strips_surrounding_whitespace():
    assert normalize_text("  Pedro  ") == "Pedro"
    assert normalize_text(None) == ""


def test_normalize_email_lowercases_and_strips():
    assert normalize_email("  Usuario@Example.COM  ") == "usuario@example.com"


def test_is_valid_email_accepts_well_formed_addresses():
    assert is_valid_email("usuario@example.com") is True
    assert is_valid_email("a.b+c@sub.example.co") is True


def test_is_valid_email_rejects_malformed_addresses():
    assert is_valid_email("correo-invalido") is False
    assert is_valid_email("falta-arroba.com") is False
    assert is_valid_email("@example.com") is False
    assert is_valid_email("usuario@") is False


def test_is_valid_password_enforces_minimum_length():
    assert is_valid_password("PasswordSeguro123!") is True
    assert is_valid_password("short1") is False
    assert is_valid_password("") is False
    assert is_valid_password(None) is False
