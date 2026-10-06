"""
In-memory session of the logged-in user.

Tokens live ONLY here, in memory: never written to disk, never logged,
never shown. repr() masks them so they cannot leak through a traceback or
a debug print. Thread-safe: HTTP calls run in worker threads.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading


ROLE_USER = 1
ROLE_ADMIN = 2
ROLE_NAMES = {ROLE_USER: "USER", ROLE_ADMIN: "ADMIN"}


@dataclass(frozen=True)
class SessionSnapshot:
    user_id: int
    role_id: int
    email: str

    @property
    def is_admin(self) -> bool:
        return self.role_id == ROLE_ADMIN

    @property
    def role_name(self) -> str:
        return ROLE_NAMES.get(self.role_id, f"ROLE {self.role_id}")


class Session:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user: SessionSnapshot | None = None

    def __repr__(self) -> str:
        user = self.user
        who = f"user_id={user.user_id}, role_id={user.role_id}" if user else "anonymous"
        return f"Session({who}, access_token='***', refresh_token='***')"

    # -- writes -----------------------------------------------------------------

    def start(self, access_token: str, refresh_token: str, user: dict) -> None:
        """`user` is the login/refresh payload: {"id", "email", "role_id"}."""
        snapshot = SessionSnapshot(user_id=int(user["id"]), role_id=int(user["role_id"]), email=str(user.get("email") or ""))
        with self._lock:
            self._access_token = access_token
            self._refresh_token = refresh_token
            self._user = snapshot

    def update_tokens(self, access_token: str, refresh_token: str, user: dict | None = None) -> None:
        """After /refresh (rotation): both tokens change; role may change too."""
        with self._lock:
            if self._user is None:
                return  # logged out meanwhile: do not resurrect the session
            self._access_token = access_token
            self._refresh_token = refresh_token
            if user:
                self._user = SessionSnapshot(
                    user_id=int(user.get("id", self._user.user_id)),
                    role_id=int(user.get("role_id", self._user.role_id)),
                    email=str(user.get("email") or self._user.email),
                )

    def clear(self) -> None:
        with self._lock:
            self._access_token = None
            self._refresh_token = None
            self._user = None

    # -- reads ------------------------------------------------------------------

    @property
    def access_token(self) -> str | None:
        with self._lock:
            return self._access_token

    @property
    def refresh_token(self) -> str | None:
        with self._lock:
            return self._refresh_token

    @property
    def user(self) -> SessionSnapshot | None:
        with self._lock:
            return self._user

    @property
    def is_authenticated(self) -> bool:
        with self._lock:
            return self._access_token is not None and self._user is not None

    @property
    def is_admin(self) -> bool:
        user = self.user
        return bool(user and user.is_admin)
