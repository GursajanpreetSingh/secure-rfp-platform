from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import DUMMY_HASH, verify_password
from app.models import User

MAX_EMAIL_LENGTH = 255


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the credentials are valid and the account is active, else None.

    Every failure looks the same to the caller, and exactly one password check is always done,
    so response time does not reveal whether an email exists.
    """
    email = email.strip().lower()

    user = None
    if 0 < len(email) <= MAX_EMAIL_LENGTH:
        user = db.scalar(select(User).where(User.email == email))

    password_hash = user.password_hash if user is not None else DUMMY_HASH
    password_ok = verify_password(password, password_hash)

    if user is None or not password_ok or not user.is_active:
        return None
    return user
