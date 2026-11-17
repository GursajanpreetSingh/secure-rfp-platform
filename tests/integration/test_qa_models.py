import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import QaConversation, QaMessage, User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration


def make_user(db, email="qa-models@modeltest.test"):
    user = User(
        email=email,
        password_hash="not-a-real-hash",
        role=Role.EXTERNAL,
        clearance=Classification.PUBLIC,
    )
    db.add(user)
    db.flush()
    return user


def make_conversation(db, user):
    conversation = QaConversation(user_id=user.id, title="Uptime question")
    db.add(conversation)
    db.flush()
    return conversation


def message(conversation, position=1, **overrides):
    values = {
        "conversation_id": conversation.id,
        "position": position,
        "role": "user",
        "content": "What is the uptime?",
    }
    values.update(overrides)
    return QaMessage(**values)


def test_defaults(db_session):
    conversation = make_conversation(db_session, make_user(db_session))
    row = message(conversation)
    db_session.add(row)
    db_session.flush()
    assert (row.status, row.citations, row.model) == ("asked", [], None)
    assert conversation.created_at is not None and conversation.updated_at is not None


def test_positions_are_unique_within_a_conversation(db_session):
    conversation = make_conversation(db_session, make_user(db_session))
    db_session.add(message(conversation))
    db_session.flush()
    db_session.add(message(conversation, content="again"))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("field, value", [("role", "system"), ("status", "maybe")])
def test_database_rejects_unknown_roles_and_statuses(db_session, field, value):
    conversation = make_conversation(db_session, make_user(db_session))
    db_session.add(message(conversation, **{field: value}))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_conversation_deletes_its_messages(db_session):
    conversation = make_conversation(db_session, make_user(db_session))
    db_session.add(message(conversation))
    db_session.flush()
    db_session.delete(conversation)
    db_session.flush()
    db_session.expire_all()
    assert db_session.scalars(select(QaMessage)).all() == []


def test_deleting_a_user_deletes_their_chats(db_session):
    user = make_user(db_session)
    conversation = make_conversation(db_session, user)
    db_session.add(message(conversation))
    db_session.flush()
    db_session.delete(user)
    db_session.flush()
    db_session.expire_all()
    assert db_session.scalars(select(QaConversation)).all() == []
