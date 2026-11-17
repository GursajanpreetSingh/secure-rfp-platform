import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.auth import signup
from app.core.db import get_db
from app.models import AuditEvent, User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration

GOOD = "correct horse battery"


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def email():
    return f"new-{uuid.uuid4().hex[:8]}@signuptest.test"


def body(address=None, **overrides):
    values = {"email": address or email(), "password": GOOD, "full_name": "Asha Rao"}
    values.update(overrides)
    return values


def test_signup_creates_the_weakest_kind_of_account_and_signs_in(db_session, client):
    address = email().upper()
    response = client.post("/auth/register", json=body(address))
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["access_token"]

    user = db_session.scalar(select(User).where(User.email == address.lower()))
    assert (user.role, user.clearance, user.department) == (
        Role.EXTERNAL,
        Classification.PUBLIC,
        None,
    )
    assert user.is_active and user.full_name == "Asha Rao"
    assert user.password_hash != GOOD

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "external"


def test_a_role_cannot_be_requested(client):
    for field in ("role", "clearance", "department", "is_active"):
        response = client.post("/auth/register", json=body(**{field: "admin"}))
        assert response.status_code == 422


def test_the_new_user_can_log_in_again(client):
    address = email()
    client.post("/auth/register", json=body(address))
    login = client.post("/auth/login", json={"email": address, "password": GOOD})
    assert login.status_code == 200


def test_new_accounts_cannot_start_an_rfp_run(client):
    token = client.post("/auth/register", json=body()).json()["access_token"]
    response = client.post(
        "/rfp/runs",
        content=b"%PDF-1.4",
        headers={"Authorization": f"Bearer {token}", "X-Filename": "RFP-T.pdf"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"email": "a@b"},
        {"email": "two words@x.com"},
        {"full_name": "   "},
        {"full_name": "bad\x00name"},
        {"email": "boss@meridian.test"},
    ],
)
def test_bad_details_are_refused(client, overrides):
    assert client.post("/auth/register", json=body(**overrides)).status_code == 422


@pytest.mark.parametrize("password", ["short", "x" * 129, ""])
def test_bad_passwords_are_refused_without_echoing_them(client, password):
    response = client.post("/auth/register", json=body(password=password))
    assert response.status_code == 422
    if password:
        assert password not in response.text


def test_the_same_email_cannot_register_twice_even_in_another_case(client):
    address = email()
    assert client.post("/auth/register", json=body(address)).status_code == 201
    assert client.post("/auth/register", json=body(address.upper())).status_code == 409


def test_signup_is_audited_without_the_password(db_session, client):
    address = email()
    client.post("/auth/register", json=body(address))
    user = db_session.scalar(select(User).where(User.email == address))
    event = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "account_created", AuditEvent.user_id == user.id
        )
    ).one()
    assert event.user_email == address
    assert GOOD not in str(event.detail)


def test_a_flood_of_signups_is_slowed_down(client, monkeypatch):
    monkeypatch.setattr(signup, "MAX_SIGNUPS_PER_HOUR", 0)
    assert client.post("/auth/register", json=body()).status_code == 429
