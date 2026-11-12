import uuid

from app.auth.policy_types import Resource, Subject
from app.models.enums import Classification, DocStatus, Role


def make_subject(**overrides) -> Subject:
    """A valid, active employee. Pass keyword arguments to change any field."""
    values = {
        "id": uuid.uuid4(),
        "role": Role.EMPLOYEE,
        "department": "sales",
        "clearance": Classification.INTERNAL,
        "is_active": True,
    }
    values.update(overrides)
    return Subject(**values)


def make_resource(**overrides) -> Resource:
    """An active internal document that employees may use for RFPs."""
    values = {
        "classification": Classification.INTERNAL,
        "department": None,
        "allowed_roles": frozenset({"employee"}),
        "allowed_purposes": frozenset({"rfp"}),
        "status": DocStatus.ACTIVE,
        "valid_until": None,
    }
    values.update(overrides)
    return Resource(**values)
