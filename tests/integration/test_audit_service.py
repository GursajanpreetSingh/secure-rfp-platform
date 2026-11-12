import uuid

import pytest
from sqlalchemy import func, select

from app.audit.service import AuditAction, record_decision, record_event
from app.auth.policy_types import Decision, Reason
from app.models import AuditEvent, User
from app.models.enums import AuditDecision, Classification, Purpose, Role

pytestmark = pytest.mark.integration


def make_user(db):
    user = User(
        email="auditor1@audittest.test",
        password_hash="not-a-real-hash",
        role=Role.AUDITOR,
        clearance=Classification.CONFIDENTIAL,
    )
    db.add(user)
    db.flush()
    return user


def count_events(db):
    return db.scalar(select(func.count()).select_from(AuditEvent))


def test_event_without_a_user(db_session):
    event = record_event(
        db_session, AuditAction.LOGIN_FAILURE, AuditDecision.DENY, detail={"attempt": 1}
    )
    assert event.id is not None
    assert event.occurred_at is not None
    assert event.action == "login_failure"
    assert event.decision == AuditDecision.DENY
    assert event.user_id is None
    assert event.user_email is None
    assert event.user_role is None
    assert event.detail == {"attempt": 1}


def test_user_details_are_copied_into_the_event(db_session):
    user = make_user(db_session)
    event = record_event(db_session, AuditAction.LOGIN_SUCCESS, AuditDecision.ALLOW, user=user)
    assert event.user_id == user.id
    assert event.user_email == "auditor1@audittest.test"
    assert event.user_role == "auditor"


def test_purpose_enum_is_stored_as_text(db_session):
    event = record_event(db_session, AuditAction.ACCESS_DECISION, purpose=Purpose.RFP)
    assert event.purpose == "rfp"


def test_uuid_resource_id_is_stored_as_text(db_session):
    resource_id = uuid.uuid4()
    event = record_event(
        db_session, AuditAction.ACCESS_DECISION, resource_type="document", resource_id=resource_id
    )
    assert event.resource_id == str(resource_id)


def test_unknown_action_is_rejected(db_session):
    before = count_events(db_session)
    with pytest.raises(ValueError):
        record_event(db_session, "made_up_action")
    assert count_events(db_session) == before


@pytest.mark.parametrize(
    "field",
    [
        {"resource_type": "x" * 41},
        {"resource_id": "x" * 65},
        {"request_id": "x" * 65},
        {"purpose": "x" * 21},
    ],
)
def test_overlong_fields_are_rejected(db_session, field):
    before = count_events(db_session)
    with pytest.raises(ValueError):
        record_event(db_session, AuditAction.ACCESS_DECISION, **field)
    assert count_events(db_session) == before


def test_a_secret_in_the_detail_is_refused_and_nothing_is_saved(db_session):
    before = count_events(db_session)
    with pytest.raises(ValueError):
        record_event(db_session, AuditAction.LOGIN_FAILURE, detail={"password": "hunter2"})
    assert count_events(db_session) == before


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (Decision(True, Reason.GENERAL_ACCESS), AuditDecision.ALLOW),
        (Decision(False, Reason.CLEARANCE_TOO_LOW), AuditDecision.DENY),
    ],
)
def test_policy_decisions_are_recorded_with_only_the_reason_code(db_session, decision, expected):
    user = make_user(db_session)
    document_id = uuid.uuid4()

    event = record_decision(db_session, user, document_id, Purpose.RFP, decision)

    assert event.action == "access_decision"
    assert event.decision == expected
    assert event.resource_type == "document"
    assert event.resource_id == str(document_id)
    assert event.purpose == "rfp"
    assert event.detail == {"reason": decision.reason.value}
