"""
Password hashing compatible with the Login microservice.

Login verifies passwords with bcrypt.checkpw against usuarios.password_hash
(apps/services/login/services/auth_service.py), and the monolith writes
bcryptjs hashes. Users therefore writes standard bcrypt hashes ($2b$...)
with the same cost Login uses for new hashes. bcrypt hashes carry their own
salt and cost, so Login can verify them without any shared code.
"""

from __future__ import annotations

import bcrypt


BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("utf-8")
