import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token, decode_access_token
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration

GOOD = "correct horse battery"
EMAIL = "alice@apitest.test"
INACTIVE_EMAIL = "inactive@apitest.test"
GENERIC_401 = {"detail": "invalid or missing credentials"}


@pytest.fixture
def client(db_session):
    """A test client whose API calls use the same rolled-back database transaction."""
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def create_user(db, email=EMAIL, is_active=True, role=Role.EMPLOYEE):
    user = User(
        email=email,
        password_hash=hash_password(GOOD),
        full_name="Alice Test",
        role=role,
        department="sales",
        clearance=Classification.INTERNAL,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def login(client, email=EMAIL, password=GOOD):
    return client.post("/auth/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


# ---- login ----


def test_login_returns_a_token_that_identifies_the_user(client, db_session):
    user = create_user(db_session)
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().jwt_expire_minutes * 60
    assert decode_access_token(body["access_token"]).user_id == user.id


def test_login_response_is_not_cacheable(client, db_session):
    create_user(db_session)
    assert login(client).headers["cache-control"] == "no-store"


def test_login_failures_all_look_the_same(client, db_session):
    create_user(db_session)
    create_user(db_session, email=INACTIVE_EMAIL, is_active=False)

    wrong_password = login(client, EMAIL, "a wrong password here")
    unknown_email = login(client, "nobody@apitest.test", GOOD)
    inactive_user = login(client, INACTIVE_EMAIL, GOOD)

    for response in (wrong_password, unknown_email, inactive_user):
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid credentials"}


def test_login_extra_field_is_rejected_without_echoing_the_password(client):
    secret = "supersecret-xyz-123"
    response = client.post("/auth/login", json={"email": EMAIL, "password": secret, "foo": 1})
    assert response.status_code == 422
    assert secret not in response.text


@pytest.mark.parametrize("body", [{}, {"email": EMAIL}, {"password": GOOD}])
def test_login_with_missing_fields_is_rejected(client, body):
    assert client.post("/auth/login", json=body).status_code == 422


# ---- protected route: /auth/me ----


def test_me_returns_profile_without_password_hash(client, db_session):
    user = create_user(db_session)
    token = create_access_token(user.id)

    response = client.get("/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "role", "department", "clearance"}
    assert body["id"] == str(user.id)
    assert body["email"] == EMAIL
    assert body["role"] == "employee"
    assert body["clearance"] == "internal"
    assert "password" not in response.text
    assert "argon2" not in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer garbage"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer"},
    ],
)
def test_me_rejects_missing_or_malformed_credentials(client, headers):
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json() == GENERIC_401


def test_expired_token_is_rejected(client, db_session):
    user = create_user(db_session)
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-5))
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_forged_signature_is_rejected(client, db_session):
    user = create_user(db_session)
    header, payload, signature = create_access_token(user.id).split(".")
    broken = ("A" if signature[0] != "A" else "B") + signature[1:]
    forged = f"{header}.{payload}.{broken}"
    assert client.get("/auth/me", headers=auth_header(forged)).status_code == 401


def test_token_for_unknown_user_is_rejected(client):
    token = create_access_token(uuid.uuid4())
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_disabled_user_with_valid_token_is_rejected(client, db_session):
    user = create_user(db_session)
    token = create_access_token(user.id)
    assert client.get("/auth/me", headers=auth_header(token)).status_code == 200

    user.is_active = False
    db_session.flush()

    assert client.get("/auth/me", headers=auth_header(token)).status_code == 401


def test_role_change_takes_effect_immediately(client, db_session):
    user = create_user(db_session)
    token = create_access_token(user.id)
    assert client.get("/auth/me", headers=auth_header(token)).json()["role"] == "employee"

    user.role = Role.AUDITOR
    db_session.flush()

    assert client.get("/auth/me", headers=auth_header(token)).json()["role"] == "auditor"


def test_every_401_reply_is_identical(client, db_session):
    user = create_user(db_session)
    disabled = create_user(db_session, email=INACTIVE_EMAIL, is_active=False)

    replies = [
        client.get("/auth/me"),
        client.get(
            "/auth/me",
            headers=auth_header(create_access_token(user.id, expires_delta=timedelta(seconds=-5))),
        ),
        client.get("/auth/me", headers=auth_header(create_access_token(disabled.id))),
        client.get("/auth/me", headers=auth_header(create_access_token(uuid.uuid4()))),
    ]

    for reply in replies:
        assert reply.status_code == 401
        assert reply.json() == GENERIC_401
        assert reply.headers["www-authenticate"] == "Bearer"
        assert reply.headers["cache-control"] == "no-store"


def test_401_tells_the_client_to_use_bearer(client):
    assert client.get("/auth/me").headers["www-authenticate"] == "Bearer"
