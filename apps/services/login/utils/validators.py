from __future__ import annotations

import re


# Deliberately simple (structure, not full RFC 5322 compliance): the
# database still enforces uniqueness, and this is only a first filter
# before ever touching PostgreSQL.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def normalize_email(email: str | None) -> str:
    return normalize_text(email).lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def is_valid_password(password: str | None) -> bool:
    return bool(password) and len(password) >= MIN_PASSWORD_LENGTH
