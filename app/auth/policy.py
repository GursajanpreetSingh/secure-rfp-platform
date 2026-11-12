from datetime import date

from app.auth.policy_types import AclEntry, Decision, Reason, Resource, Subject
from app.models.enums import AclEffect, Classification, DocStatus, Purpose, Role, SubjectType

_VALID_PURPOSES = frozenset(p.value for p in Purpose)


def _deny(reason: Reason) -> Decision:
    return Decision(allowed=False, reason=reason)


def _allow(reason: Reason) -> Decision:
    return Decision(allowed=True, reason=reason)


def _entry_names_subject(entry: AclEntry, subject: Subject) -> bool:
    """True if this explicit rule applies to the user, either by id or through their role."""
    if entry.subject_type == SubjectType.USER:
        return entry.subject_id == str(subject.id)
    if entry.subject_type == SubjectType.ROLE:
        return entry.subject_id == subject.role.value
    return False


def decide(
    subject: Subject,
    resource: Resource,
    purpose: Purpose | str,
    today: date,
) -> Decision:
    """May this user use this document for this purpose? The first matching rule decides."""
    purpose_value = purpose.value if isinstance(purpose, Purpose) else str(purpose)

    # 1. A disabled account never gets anything.
    if not subject.is_active:
        return _deny(Reason.USER_INACTIVE)

    # 2. Only active documents can be used (not draft, superseded, archived or unreadable).
    if resource.status != DocStatus.ACTIVE:
        return _deny(Reason.DOCUMENT_NOT_ACTIVE)

    # 3. Expired documents cannot be evidence for an RFP.
    if (
        purpose_value == Purpose.RFP.value
        and resource.valid_until is not None
        and resource.valid_until < today
    ):
        return _deny(Reason.DOCUMENT_EXPIRED)

    # 4. Purpose limitation: the document must list this purpose. An empty list means none.
    if purpose_value not in _VALID_PURPOSES or purpose_value not in resource.allowed_purposes:
        return _deny(Reason.PURPOSE_NOT_ALLOWED)

    # 5. An explicit deny always wins.
    applicable = [e for e in resource.acl if _entry_names_subject(e, subject)]
    if any(e.effect == AclEffect.DENY for e in applicable):
        return _deny(Reason.EXPLICIT_DENY)

    # 6. An explicit allow grants access, even without the usual clearance or department.
    if any(e.effect == AclEffect.ALLOW for e in applicable):
        return _allow(Reason.EXPLICIT_ALLOW)

    # 7. Administrators run the system but get no content through the general path.
    if subject.role == Role.ADMIN:
        return _deny(Reason.ADMIN_NO_CONTENT_ACCESS)

    # 8. Restricted documents are reachable only through an explicit allow (rule 6).
    if resource.classification == Classification.RESTRICTED:
        return _deny(Reason.RESTRICTED_NEEDS_GRANT)

    # 9. The user's role must be listed on the document. An empty list means nobody.
    if subject.role.value not in resource.allowed_roles:
        return _deny(Reason.ROLE_NOT_ALLOWED)

    # 10. The user's clearance must be at least the document's classification.
    if subject.clearance.level < resource.classification.level:
        return _deny(Reason.CLEARANCE_TOO_LOW)

    # 11. Confidential documents also need the same department. Missing departments never match.
    if resource.classification == Classification.CONFIDENTIAL and (
        subject.department is None or resource.department != subject.department
    ):
        return _deny(Reason.DEPARTMENT_MISMATCH)

    # 12. Every check passed.
    return _allow(Reason.GENERAL_ACCESS)
