from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.tokens import TokenError, decode_access_token
from app.core.db import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    """One identical 401 for every authentication failure."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Return the logged-in user, loaded fresh from the database on every request."""
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError:
        raise unauthorized() from None

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user
