from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import settings

COOKIE = "__Host-logbook" if settings.cookie_secure else "logbook"
SESSION_TTL = timedelta(days=7)
USERNAME_PATTERN = r"^[a-z0-9][a-z0-9_.-]{2,63}$"
hasher = PasswordHasher()
dummy_hash = hasher.hash(token_urlsafe(32))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def new_session() -> str:
    return token_urlsafe(32)


def session_hash(token: str) -> bytes:
    return sha256(token.encode()).digest()


