from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()

# A valid hash of a throwaway password. The login code will verify against this when an email
# does not exist, so "unknown user" takes as long as "wrong password" (no timing leak).
DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    """Return an Argon2id hash of the password. Rejects passwords that are too short or too long."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long"
        )
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return True only if the password matches the hash. Never raises on bad input."""
    if len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with older settings and should be refreshed at next login."""
    return _hasher.check_needs_rehash(password_hash)
