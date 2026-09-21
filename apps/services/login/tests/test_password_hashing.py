import bcrypt

from services.auth_service import _check_password, _hash_password


def test_hash_password_roundtrip():
    password = "PasswordSeguro123!"
    hashed = _hash_password(password)

    assert hashed != password
    assert _check_password(password, hashed) is True
    assert _check_password("wrong-password", hashed) is False


def test_check_password_is_compatible_with_bcryptjs_style_hashes():
    # The monolith hashes passwords with bcryptjs at cost 10 ($2a$/$2b$
    # prefix). Simulate that here with plain bcrypt (the same algorithm)
    # to confirm this service can validate those existing hashes without
    # migrating them.
    password = "LegacyPassword123!"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")

    assert _check_password(password, legacy_hash) is True
    assert _check_password("incorrect", legacy_hash) is False


def test_check_password_rejects_malformed_stored_hash():
    assert _check_password("anything", "not-a-real-bcrypt-hash") is False
