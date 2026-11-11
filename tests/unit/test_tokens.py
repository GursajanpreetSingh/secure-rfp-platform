import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.tokens import (
    AUDIENCE,
    ISSUER,
    TokenError,
    create_access_token,
    decode_access_token,
)
from app.core.config import get_settings


def secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def base_claims(**overrides) -> dict:
    """Valid claims. Passing name=None removes that claim, for 'missing claim' tests."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "jti": uuid.uuid4().hex,
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def test_roundtrip_returns_same_user():
    user_id = uuid.uuid4()
    claims = decode_access_token(create_access_token(user_id))
    assert claims.user_id == user_id
    assert claims.expires_at > datetime.now(UTC)


def test_token_carries_no_role_or_email():
    token = create_access_token(uuid.uuid4())
    payload = jwt.decode(token, options={"verify_signature": False})
    assert set(payload) == {"sub", "iat", "exp", "iss", "aud", "jti"}


def test_each_token_has_a_unique_id():
    user_id = uuid.uuid4()
    first = decode_access_token(create_access_token(user_id))
    second = decode_access_token(create_access_token(user_id))
    assert first.token_id != second.token_id


def test_expired_token_is_rejected():
    token = create_access_token(uuid.uuid4(), expires_delta=timedelta(seconds=-5))
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_signature_is_rejected():
    header, payload, signature = create_access_token(uuid.uuid4()).split(".")
    broken = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(TokenError):
        decode_access_token(f"{header}.{payload}.{broken}")


def test_payload_swapped_from_another_token_is_rejected():
    first = create_access_token(uuid.uuid4()).split(".")
    second = create_access_token(uuid.uuid4()).split(".")
    with pytest.raises(TokenError):
        decode_access_token(f"{first[0]}.{second[1]}.{first[2]}")


def test_wrong_secret_is_rejected():
    token = jwt.encode(base_claims(), "x" * 40, algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize("overrides", [{"aud": "some-other-api"}, {"iss": "someone-else"}])
def test_wrong_audience_or_issuer_is_rejected(overrides):
    token = jwt.encode(base_claims(**overrides), secret(), algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "iss", "aud", "jti"])
def test_missing_required_claim_is_rejected(missing):
    token = jwt.encode(base_claims(**{missing: None}), secret(), algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_subject_must_be_a_uuid():
    token = jwt.encode(base_claims(sub="not-a-uuid"), secret(), algorithm="HS256")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_unsigned_token_is_rejected():
    token = jwt.encode(base_claims(), None, algorithm="none")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_other_algorithm_is_rejected():
    token = jwt.encode(base_claims(), secret(), algorithm="HS512")
    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "...."])
def test_garbage_is_rejected(garbage):
    with pytest.raises(TokenError):
        decode_access_token(garbage)
