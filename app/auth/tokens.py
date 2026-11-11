import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

ISSUER = "secure-rfp-platform"
AUDIENCE = "rfp-api"
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
_REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud", "jti"]


class TokenError(Exception):
    """The token is missing, malformed, expired or not trustworthy."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    token_id: str
    expires_at: datetime


def _settings():
    settings = get_settings()
    if settings.jwt_algorithm not in _ALLOWED_ALGORITHMS:
        raise RuntimeError("JWT_ALGORITHM must be HS256, HS384 or HS512")
    return settings


def create_access_token(user_id: uuid.UUID, expires_delta: timedelta | None = None) -> str:
    """Create a signed token that identifies the user. It deliberately carries no role."""
    settings = _settings()
    now = datetime.now(UTC)
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + lifetime,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> TokenClaims:
    """Verify a token and return its claims. Raises TokenError for any problem."""
    settings = _settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": _REQUIRED_CLAIMS},
        )
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise TokenError("invalid token") from exc
    return TokenClaims(
        user_id=user_id,
        token_id=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )
