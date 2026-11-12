import uuid
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.models.enums import AclEffect, Classification, DocStatus, Role, SubjectType


class Reason(StrEnum):
    """Why a decision was made. For the audit log only. Never show this to the end user."""

    USER_INACTIVE = "user_inactive"
    DOCUMENT_NOT_ACTIVE = "document_not_active"
    DOCUMENT_EXPIRED = "document_expired"
    PURPOSE_NOT_ALLOWED = "purpose_not_allowed"
    EXPLICIT_DENY = "explicit_deny"
    EXPLICIT_ALLOW = "explicit_allow"
    ADMIN_NO_CONTENT_ACCESS = "admin_no_content_access"
    RESTRICTED_NEEDS_GRANT = "restricted_needs_grant"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    CLEARANCE_TOO_LOW = "clearance_too_low"
    DEPARTMENT_MISMATCH = "department_mismatch"
    GENERAL_ACCESS = "general_access"


@dataclass(frozen=True)
class Subject:
    """The person asking. Built from a user row, but holds plain values only."""

    id: uuid.UUID
    role: Role
    department: str | None
    clearance: Classification
    is_active: bool


@dataclass(frozen=True)
class AclEntry:
    """One explicit rule on a document: allow or deny a specific user or a whole role."""

    subject_type: SubjectType
    subject_id: str
    effect: AclEffect


@dataclass(frozen=True)
class Resource:
    """The document being asked about, with its access rules."""

    classification: Classification
    department: str | None
    allowed_roles: frozenset[str]
    allowed_purposes: frozenset[str]
    status: DocStatus
    valid_until: date | None
    acl: tuple[AclEntry, ...] = ()


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: Reason
