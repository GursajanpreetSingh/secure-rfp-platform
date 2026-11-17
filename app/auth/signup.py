"""Self-service sign-up. New accounts are always the least powerful kind.

A person who signs up gets role "external" and clearance "public", the same as the demo client.
That role can use question answering, but it cannot start an RFP run, and the policy shows it
only documents that were explicitly opened to outsiders. Staff roles are never granted here;
an administrator sets them. Nothing in the request can choose a role.

Known limit, written down on purpose: there is no email verification, so someone can register
an address they do not own. The account has no extra power, so the damage is limited to using
the low-privilege features under a name that is not theirs.
"""

import re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.models import User
from app.models.enums import Classification, Role

MAX_SIGNUPS_PER_HOUR = 30  # across the whole system; a brake on bulk sign-up, not per person
RESERVED_DOMAINS = ("meridian.test",)  # staff addresses are created by an administrator only
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SignupError(ValueError):
    """The sign-up request is not acceptable. The message is safe to show."""


class DuplicateEmail(SignupError):
    pass


class TooManySignups(SignupError):
    pass


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=255)
    # No rules here on purpose: validation errors echo the input, and a password must not be
    # echoed. create_account checks it and reports only the rule that failed.
    password: str
    full_name: str = Field(max_length=120)


def create_account(db: Session, email: str, password: str, full_name: str) -> User:
    email = email.strip().lower()
    full_name = " ".join(full_name.split())

    if not _EMAIL.match(email):
        raise SignupError("Enter a valid email address.")
    if email.rsplit("@", 1)[1] in RESERVED_DOMAINS:
        raise SignupError("That email address cannot be used to sign up.")
    if not full_name or _CONTROL.search(full_name):
        raise SignupError("Enter your name.")
    try:
        password_hash = hash_password(password)
    except ValueError as problem:
        raise SignupError(str(problem).capitalize() + ".") from None

    recent = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.created_at > datetime.now(UTC) - timedelta(hours=1))
    )
    if recent >= MAX_SIGNUPS_PER_HOUR:
        raise TooManySignups("Too many new accounts right now. Try again later.")

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise DuplicateEmail("An account with this email already exists.")

    user = User(
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=Role.EXTERNAL,
        department=None,
        clearance=Classification.PUBLIC,
        is_active=True,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError:
        raise DuplicateEmail("An account with this email already exists.") from None
    return user
