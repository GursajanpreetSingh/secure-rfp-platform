import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.main import app
from app.api.routes import auth as auth_routes
from app.audit.service import email_digest
from app.auth.passwords import hash_password
from app.core.db import get_db
from app.models import AuditEvent, User
from app.models.enums import AuditDecision, Classification, Role

pytestmark = pytest.mark.integration

GOOD = "correct horse battery"
EMAIL = "alice@loginaudit.test"


@pytest.fixture
def client(db_session):
    """Calls the API inside the test's rolled-back transaction. Server errors become 500s."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def create_user(db, email=EMAIL, is_active=True):
    user = User(
        email=email,
        password_hash=hash_password(GOOD),
        full_name="Alice",
        role=Role.EMPLOYEE,
        department="sales",
        clearance=Classification.INTERNAL,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def last_event_id(db):
    return db.scalar(select(func.coalesce(func.max(AuditEvent.id), 0)))


def events_since(db, last_id):
    query = select(AuditEvent).where(AuditEvent.id > last_id).order_by(AuditEvent.id)
    return db.scalars(query).all()


def row_text(event):
    """Every column of an audit row as one lowercase string, for 'never contains' checks."""
    parts = [
        event.action,
        event.decision.value,
        str(event.user_id),
        str(event.user_email),
        str(event.user_role),
        str(event.resource_type),
        str(event.resource_id),
        str(event.purpose),
        json.dumps(event.detail),
        str(event.request_id),
    ]
    return " ".join(parts).lower()


def login(client, email=EMAIL, password=GOOD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_successful_login_is_recorded(client, db_session):
    user = create_user(db_session)
    before = last_event_id(db_session)

    assert login(client).status_code == 200

    (event,) = events_since(db_session, before)
    assert event.action == "login_success"
    assert event.decision == AuditDecision.ALLOW
    assert event.user_id == user.id
    assert event.user_email == EMAIL
    assert event.user_role == "employee"
    assert event.detail == {}


def test_failed_login_for_unknown_email_is_recorded_without_the_typed_text(client, db_session):
    before = last_event_id(db_session)

    response = login(client, "Nobody@LoginAudit.test", GOOD)

    assert response.status_code == 401
    (event,) = events_since(db_session, before)
    assert event.action == "login_failure"
    assert event.decision == AuditDecision.DENY
    assert event.user_id is None
    assert event.user_email is None
    assert event.user_role is None
    assert event.detail == {"email_digest": email_digest("nobody@loginaudit.test")}
    assert "nobody" not in row_text(event)


def test_a_password_typed_into_the_email_box_is_never_stored(client, db_session):
    typed = "My-Real-Password-4321"
    before = last_event_id(db_session)

    login(client, typed, "some other password")

    (event,) = events_since(db_session, before)
    assert typed.lower() not in row_text(event)


def test_wrong_password_and_inactive_user_are_recorded_the_same_way(client, db_session):
    create_user(db_session)
    create_user(db_session, email="off@loginaudit.test", is_active=False)
    before = last_event_id(db_session)

    login(client, EMAIL, "a wrong password here")
    login(client, "off@loginaudit.test", GOOD)

    first, second = events_since(db_session, before)
    for event in (first, second):
        assert event.action == "login_failure"
        assert event.decision == AuditDecision.DENY
        assert event.user_id is None
    assert first.detail == {"email_digest": email_digest(EMAIL)}
    assert second.detail == {"email_digest": email_digest("off@loginaudit.test")}


def test_repeated_attempts_on_one_address_share_a_digest(client, db_session):
    before = last_event_id(db_session)

    login(client, "Bob@loginaudit.test", GOOD)
    login(client, "  bob@loginaudit.test ", GOOD)

    first, second = events_since(db_session, before)
    assert first.detail == second.detail
    assert first.detail["email_digest"] == email_digest("bob@loginaudit.test")


def test_malformed_requests_are_not_recorded(client, db_session):
    before = last_event_id(db_session)

    response = client.post("/auth/login", json={"email": EMAIL, "password": GOOD, "extra": 1})

    assert response.status_code == 422
    assert events_since(db_session, before) == []


def test_login_fails_closed_when_the_audit_write_fails(client, db_session, monkeypatch):
    create_user(db_session)

    def broken(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(auth_routes, "record_event", broken)

    response = login(client)

    assert response.status_code == 500
    assert "access_token" not in response.text


def test_no_token_or_password_ever_appears_in_audit_rows(client, db_session):
    create_user(db_session)
    before = last_event_id(db_session)

    success = login(client)
    login(client, EMAIL, "a wrong password here")
    token = success.json()["access_token"]

    events = events_since(db_session, before)
    assert len(events) == 2
    for event in events:
        text = row_text(event)
        assert token.lower() not in text
        assert "argon2" not in text
        assert GOOD not in text
        assert "a wrong password here" not in text
