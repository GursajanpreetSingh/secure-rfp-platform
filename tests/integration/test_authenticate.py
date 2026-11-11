import pytest

from app.auth import service
from app.auth.passwords import DUMMY_HASH, hash_password
from app.auth.service import authenticate
from app.models import User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration

GOOD = "correct horse battery"
EMAIL = "alice@authtest.test"


def create_user(db, email=EMAIL, password=GOOD, is_active=True):
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=Role.EMPLOYEE,
        clearance=Classification.INTERNAL,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def test_correct_credentials_return_the_user(db_session):
    user = create_user(db_session)
    result = authenticate(db_session, EMAIL, GOOD)
    assert result is not None
    assert result.id == user.id


def test_email_is_case_and_space_insensitive(db_session):
    user = create_user(db_session)
    result = authenticate(db_session, "  Alice@AuthTest.TEST ", GOOD)
    assert result is not None
    assert result.id == user.id


def test_wrong_password_fails(db_session):
    create_user(db_session)
    assert authenticate(db_session, EMAIL, "some other password") is None


def test_unknown_email_fails(db_session):
    assert authenticate(db_session, "nobody@authtest.test", GOOD) is None


def test_inactive_user_fails_even_with_correct_password(db_session):
    create_user(db_session, is_active=False)
    assert authenticate(db_session, EMAIL, GOOD) is None


@pytest.mark.parametrize(
    ("email", "password"),
    [
        (EMAIL, ""),
        (EMAIL, "x" * 200),
        ("", GOOD),
        ("a" * 300 + "@authtest.test", GOOD),
    ],
)
def test_empty_or_oversized_input_fails(db_session, email, password):
    create_user(db_session)
    assert authenticate(db_session, email, password) is None


@pytest.fixture
def hash_checks(monkeypatch):
    """Record which hash each password check is made against."""
    calls = []
    real = service.verify_password

    def spy(password, password_hash):
        calls.append(password_hash)
        return real(password, password_hash)

    monkeypatch.setattr(service, "verify_password", spy)
    return calls


def test_unknown_email_still_does_one_hash_check(db_session, hash_checks):
    assert authenticate(db_session, "nobody@authtest.test", GOOD) is None
    assert hash_checks == [DUMMY_HASH]


def test_wrong_password_does_one_hash_check(db_session, hash_checks):
    user = create_user(db_session)
    assert authenticate(db_session, EMAIL, "some other password") is None
    assert hash_checks == [user.password_hash]


def test_inactive_user_still_does_one_hash_check(db_session, hash_checks):
    user = create_user(db_session, is_active=False)
    assert authenticate(db_session, EMAIL, GOOD) is None
    assert hash_checks == [user.password_hash]
