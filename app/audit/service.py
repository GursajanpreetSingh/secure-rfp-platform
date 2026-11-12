import hashlib
import hmac
import json
import uuid
from enum import StrEnum

from sqlalchemy.orm import Session

from app.auth.policy_types import Decision
from app.core.config import get_settings
from app.models import AuditEvent, User
from app.models.enums import AuditDecision, Purpose

MAX_DETAIL_BYTES = 4000
MAX_FIELD_LENGTHS = {
    "resource_type": 40,
    "resource_id": 64,
    "request_id": 64,
    "purpose": 20,
}

# The log records IDs and decisions, never secrets or document text.
# A detail key containing any of these words is rejected.
FORBIDDEN_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "credential",
    "content",
    "snippet",
    "hash",
)


class AuditAction(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    ACCESS_DECISION = "access_decision"


def email_digest(email: str) -> str:
    """A short keyed fingerprint of an email address.

    Lets investigators see that the same address was tried repeatedly without storing what was
    typed, because people sometimes type a password into the email box.
    """
    key = get_settings().jwt_secret.get_secret_value().encode("utf-8")
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()[:16]


def _check_keys(value) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            lowered = str(key).lower()
            for part in FORBIDDEN_KEY_PARTS:
                if part in lowered:
                    raise ValueError(f"audit detail key {key!r} is not allowed ({part})")
            _check_keys(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            _check_keys(inner)


def check_detail(detail: dict) -> dict:
    """Reject details that could leak secrets, are not plain JSON, or are too large."""
    _check_keys(detail)
    try:
        encoded = json.dumps(detail)
    except (TypeError, ValueError) as exc:
        raise ValueError("audit detail must be plain JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_DETAIL_BYTES:
        raise ValueError(f"audit detail is larger than {MAX_DETAIL_BYTES} bytes")
    return detail


def record_event(
    db: Session,
    action: AuditAction | str,
    decision: AuditDecision = AuditDecision.INFO,
    *,
    user: User | None = None,
    resource_type: str | None = None,
    resource_id: str | uuid.UUID | None = None,
    purpose: Purpose | str | None = None,
    detail: dict | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Add one audit row to the session and flush it. The caller is responsible for committing."""
    fields = {
        "resource_type": resource_type,
        "resource_id": None if resource_id is None else str(resource_id),
        "purpose": purpose.value if isinstance(purpose, Purpose) else purpose,
        "request_id": request_id,
    }
    for name, value in fields.items():
        if value is not None and len(value) > MAX_FIELD_LENGTHS[name]:
            raise ValueError(f"{name} is longer than {MAX_FIELD_LENGTHS[name]} characters")

    event = AuditEvent(
        action=AuditAction(action).value,
        decision=decision,
        user_id=user.id if user is not None else None,
        user_email=user.email if user is not None else None,
        user_role=user.role.value if user is not None else None,
        detail=check_detail(detail or {}),
        **fields,
    )
    db.add(event)
    db.flush()
    return event


def record_decision(
    db: Session,
    user: User,
    resource_id: str | uuid.UUID,
    purpose: Purpose | str,
    decision: Decision,
    *,
    request_id: str | None = None,
) -> AuditEvent:
    """Record the outcome of a policy decision about a document. Only the reason code is logged."""
    return record_event(
        db,
        AuditAction.ACCESS_DECISION,
        AuditDecision.ALLOW if decision.allowed else AuditDecision.DENY,
        user=user,
        resource_type="document",
        resource_id=resource_id,
        purpose=purpose,
        detail={"reason": decision.reason.value},
        request_id=request_id,
    )
