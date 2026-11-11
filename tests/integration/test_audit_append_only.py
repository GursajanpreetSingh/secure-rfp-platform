import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, User
from app.models.enums import AuditDecision, Classification, Role

pytestmark = pytest.mark.integration


def add_event(db, **fields):
    event = AuditEvent(action="test_event", decision=AuditDecision.INFO, detail={}, **fields)
    db.add(event)
    db.flush()
    return event


def test_events_can_be_added(db_session):
    event = add_event(db_session)
    assert event.id is not None
    assert event.occurred_at is not None


def test_update_is_blocked(db_session):
    event = add_event(db_session)
    with pytest.raises(DBAPIError) as error:
        db_session.execute(
            text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"), {"id": event.id}
        )
    assert "append-only" in str(error.value)


def test_delete_is_blocked(db_session):
    event = add_event(db_session)
    with pytest.raises(DBAPIError) as error:
        db_session.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event.id})
    assert "append-only" in str(error.value)


def test_truncate_is_blocked(db_session):
    with pytest.raises(DBAPIError) as error:
        db_session.execute(text("TRUNCATE audit_events"))
    assert "append-only" in str(error.value)


def test_deleting_a_user_keeps_the_event_and_clears_the_link(db_session):
    user = User(
        email="audituser@seedtest.test",
        password_hash="not-a-real-hash",
        role=Role.EMPLOYEE,
        clearance=Classification.PUBLIC,
    )
    db_session.add(user)
    db_session.flush()
    event = add_event(db_session, user_id=user.id)

    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})

    row = db_session.execute(
        text("SELECT user_id, action FROM audit_events WHERE id = :id"), {"id": event.id}
    ).one()
    assert row.action == "test_event"
    assert row.user_id is None
