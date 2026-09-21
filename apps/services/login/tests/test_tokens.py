from utils.tokens import generate_token, hash_token


def test_generate_token_returns_distinct_url_safe_values():
    first = generate_token()
    second = generate_token()

    assert first != second
    assert len(first) > 32
    # url-safe base64 alphabet only.
    assert all(c.isalnum() or c in "-_" for c in first)


def test_hash_token_is_deterministic_and_not_the_plain_token():
    token = generate_token()

    first_hash = hash_token(token)
    second_hash = hash_token(token)

    assert first_hash == second_hash
    assert first_hash != token
    assert len(first_hash) == 64  # sha256 hex digest


def test_hash_token_differs_for_different_tokens():
    assert hash_token("token-a") != hash_token("token-b")
