import pytest
from sqlalchemy import func, select

from app.auth.passwords import verify_password
from app.auth.seed import seed_users
from app.core.db import engine
from app.models import User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration

PASSWORD = "test-password-123456"


def make_entry(email="alice@seedtest.test", **overrides):
    entry = {
        "email": email,
        "full_name": "Alice",
        "role": "employee",
        "department": "sales",
        "clearance": "internal",
    }
    entry.update(overrides)
    return entry


def get_user(db, email):
    return db.scalar(select(User).where(User.email == email))


def test_creates_users_with_hashed_passwords(db_session):
    counts = seed_users(
        db_session, [make_entry(), make_entry("bob@seedtest.test", full_name="Bob")], PASSWORD
    )
    assert counts == {"created": 2, "updated": 0, "unchanged": 0}

    alice = get_user(db_session, "alice@seedtest.test")
    assert alice.role == Role.EMPLOYEE
    assert alice.clearance == Classification.INTERNAL
    assert alice.is_active is True
    assert alice.password_hash.startswith("$argon2id$")
    assert PASSWORD not in alice.password_hash
    assert verify_password(PASSWORD, alice.password_hash)


def test_running_twice_changes_nothing(db_session):
    seed_users(db_session, [make_entry()], PASSWORD)
    first_hash = get_user(db_session, "alice@seedtest.test").password_hash

    counts = seed_users(db_session, [make_entry()], PASSWORD)

    assert counts == {"created": 0, "updated": 0, "unchanged": 1}
    assert get_user(db_session, "alice@seedtest.test").password_hash == first_hash


def test_changed_fields_are_updated(db_session):
    seed_users(db_session, [make_entry()], PASSWORD)

    changed = make_entry(
        role="auditor", department="compliance", clearance="confidential", is_active=False
    )
    counts = seed_users(db_session, [changed], PASSWORD)

    assert counts["updated"] == 1
    user = get_user(db_session, "alice@seedtest.test")
    assert user.role == Role.AUDITOR
    assert user.department == "compliance"
    assert user.clearance == Classification.CONFIDENTIAL
    assert user.is_active is False


def test_changed_password_is_rehashed(db_session):
    seed_users(db_session, [make_entry()], PASSWORD)

    counts = seed_users(db_session, [make_entry()], "a-different-password-9999")

    assert counts["updated"] == 1
    user = get_user(db_session, "alice@seedtest.test")
    assert verify_password("a-different-password-9999", user.password_hash)
    assert not verify_password(PASSWORD, user.password_hash)


def test_email_is_normalised(db_session):
    seed_users(db_session, [make_entry("  Mixed.Case@SeedTest.TEST ")], PASSWORD)
    assert get_user(db_session, "mixed.case@seedtest.test") is not None


def test_inactive_flag_is_stored(db_session):
    seed_users(db_session, [make_entry(is_active=False)], PASSWORD)
    assert get_user(db_session, "alice@seedtest.test").is_active is False


def test_invalid_role_is_rejected_and_nothing_is_saved(db_session):
    entries = [make_entry("ok@seedtest.test"), make_entry("bad@seedtest.test", role="superuser")]
    with pytest.raises(ValueError):
        seed_users(db_session, entries, PASSWORD)
    db_session.rollback()
    assert get_user(db_session, "ok@seedtest.test") is None


def test_no_test_data_is_left_behind():
    """Runs last. Looks through a separate connection, so only committed data would show."""
    with engine.connect() as connection:
        leftover = connection.scalar(
            select(func.count()).select_from(User).where(User.email.like("%@seedtest.test"))
        )
    assert leftover == 0
