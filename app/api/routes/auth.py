from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, email_digest, record_event
from app.auth.deps import get_current_user
from app.auth.schemas import LoginRequest, TokenResponse, UserOut
from app.auth.service import authenticate
from app.auth.tokens import create_access_token
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.models.enums import AuditDecision

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.password)
    if user is None:
        # Never store what was typed: people sometimes type a password into the email box.
        record_event(
            db,
            AuditAction.LOGIN_FAILURE,
            AuditDecision.DENY,
            detail={"email_digest": email_digest(body.email)},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
        )

    # Fail closed: if this audit write fails, the request fails and no token is issued.
    record_event(db, AuditAction.LOGIN_SUCCESS, AuditDecision.ALLOW, user=user)
    db.commit()

    response.headers["Cache-Control"] = "no-store"
    expires_in = get_settings().jwt_expire_minutes * 60
    return TokenResponse(access_token=create_access_token(user.id), expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
