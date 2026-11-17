from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.auth.schemas import TokenResponse
from app.auth.signup import (
    DuplicateEmail,
    RegisterRequest,
    SignupError,
    TooManySignups,
    create_account,
)
from app.auth.tokens import create_access_token
from app.core.config import get_settings
from app.core.db import get_db
from app.models.enums import AuditDecision

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    """Create a low-privilege account and sign it in. No role can be requested."""
    try:
        user = create_account(db, body.email, body.password, body.full_name)
    except DuplicateEmail as problem:
        raise HTTPException(status.HTTP_409_CONFLICT, str(problem)) from None
    except TooManySignups as problem:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(problem)) from None
    except SignupError as problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(problem)) from None

    # Fail closed: if this audit write fails, the request fails and no token is issued.
    record_event(db, AuditAction.ACCOUNT_CREATED, AuditDecision.ALLOW, user=user)
    db.commit()

    response.headers["Cache-Control"] = "no-store"
    expires_in = get_settings().jwt_expire_minutes * 60
    return TokenResponse(access_token=create_access_token(user.id), expires_in=expires_in)
