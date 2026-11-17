import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.main import app
from app.api.routes import qa as qa_routes
from app.auth.tokens import create_access_token
from app.core.db import get_db
from app.llm.client import LLMUnavailable
from app.models import AuditEvent, QaConversation, QaMessage, User
from app.models.enums import Classification, Role
from app.qa import service
from app.qa.answer import NO_ANSWER_TEXT, AnswerOut

pytestmark = pytest.mark.integration

QUESTION = "What is the uptime commitment for production?"
GOOD = AnswerOut(
    can_answer=True,
    answer="Production uptime is committed at 99.95 percent.",
    citations=[{"ref": "E1", "quote": "monthly commitment of 99.95 percent"}],
)


class FakeLLM:
    def __init__(self):
        self.answer, self.fail, self.prompts = GOOD, False, []

    def generate(self, system, prompt, schema):
        self.prompts.append(prompt)
        if self.fail:
            raise LLMUnavailable("busy")
        return SimpleNamespace(value=self.answer, model="fake-model", tokens=1)


def fake_hit():
    return SimpleNamespace(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="DOC-005_support.pdf",
        section="SLA",
        page=2,
        content="Production uptime is covered by a monthly commitment of 99.95 percent.",
    )


@pytest.fixture
def qa(db_session):
    llm, subjects = FakeLLM(), []

    def make_search(db, subject):
        subjects.append(subject)
        return lambda question: [fake_hit()]

    backend = qa_routes.Backend(llm=llm, make_search=make_search)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[qa_routes.get_backend] = lambda: backend
    client = TestClient(app)
    client.llm, client.subjects = llm, subjects
    yield client
    app.dependency_overrides.clear()


def make_user(db, role=Role.EXTERNAL, name="chat"):
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@qatest.test",
        password_hash="not-a-real-hash",
        role=role,
        clearance=Classification.PUBLIC,
    )
    db.add(user)
    db.flush()
    return user


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def events(db, action, user_id=None):
    query = select(AuditEvent).where(AuditEvent.action == action)
    query = query.where(AuditEvent.user_id == user_id if user_id else AuditEvent.user_id.is_(None))
    return db.scalars(query.order_by(AuditEvent.id)).all()


# --- public ---------------------------------------------------------------------------------


def test_public_question_is_answered_as_the_guest_and_nothing_is_saved(db_session, qa):
    before = (count(db_session, QaConversation), count(db_session, QaMessage))
    response = qa.post("/qa/public/ask", json={"question": QUESTION})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["sources"][0]["title"] == "DOC-005_support.pdf"
    assert response.headers["cache-control"] == "no-store"
    assert (count(db_session, QaConversation), count(db_session, QaMessage)) == before
    assert qa.subjects == [service.GUEST]
    assert (service.GUEST.role, service.GUEST.clearance) == (Role.EXTERNAL, Classification.PUBLIC)


def test_public_question_leaves_only_a_metadata_audit_row(db_session, qa):
    qa.post("/qa/public/ask", json={"question": QUESTION})
    row = events(db_session, "qa_asked")[-1]
    assert row.resource_type == "qa_public"
    assert row.detail["question_length"] == len(QUESTION)
    assert "uptime commitment" not in str(row.detail)
    assert "99.95" not in str(row.detail)


def test_public_endpoint_refuses_bad_input_and_floods(db_session, qa, monkeypatch):
    assert qa.post("/qa/public/ask", json={"question": "   "}).status_code == 422
    assert qa.post("/qa/public/ask", json={"question": "x" * 1001}).status_code == 422
    assert qa.post("/qa/public/ask", json={"question": "x" * 2001}).status_code == 422
    assert qa.post("/qa/public/ask", json={"question": "hi there", "role": "x"}).status_code == 422
    monkeypatch.setattr(service, "MAX_PUBLIC_QUESTIONS_PER_HOUR", 0)
    assert qa.post("/qa/public/ask", json={"question": QUESTION}).status_code == 429


def test_public_answer_says_so_when_the_model_cannot_answer(qa):
    qa.llm.answer = AnswerOut(can_answer=False, answer="", citations=[])
    body = qa.post("/qa/public/ask", json={"question": QUESTION}).json()
    assert (body["status"], body["text"], body["sources"]) == ("no_answer", NO_ANSWER_TEXT, [])


# --- logged in ------------------------------------------------------------------------------


def test_chat_needs_a_login(qa):
    assert qa.post("/qa/ask", json={"question": QUESTION}).status_code == 401
    assert qa.get("/qa/conversations").status_code == 401
    assert qa.get(f"/qa/conversations/{uuid.uuid4()}").status_code == 401


def test_a_chat_is_saved_and_continued(db_session, qa):
    user = make_user(db_session)
    first = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).json()
    assert first["status"] == "answered"
    assert first["title"] == QUESTION
    cid = first["conversation_id"]
    assert qa.subjects[-1].id == user.id

    follow = {"question": "and what about weekends?", "conversation_id": cid}
    second = qa.post("/qa/ask", json=follow, headers=auth(user)).json()
    assert second["conversation_id"] == cid
    assert QUESTION in qa.llm.prompts[1]  # earlier messages were passed along as context

    rows = db_session.scalars(
        select(QaMessage)
        .where(QaMessage.conversation_id == uuid.UUID(cid))
        .order_by(QaMessage.position)
    ).all()
    assert [(r.position, r.role) for r in rows] == [
        (1, "user"),
        (2, "assistant"),
        (3, "user"),
        (4, "assistant"),
    ]
    assert rows[1].model == "fake-model" and rows[1].status == "answered"


def test_the_chat_audit_row_has_ids_and_counts_but_no_text(db_session, qa):
    user = make_user(db_session)
    qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user))
    row = events(db_session, "qa_asked", user.id)[-1]
    assert row.detail["status"] == "answered"
    assert row.detail["question_length"] == len(QUESTION)
    assert len(row.detail["documents_cited"]) == 1
    assert "uptime" not in str(row.detail).lower()


def test_only_my_chats_are_listed(db_session, qa):
    mine, other = make_user(db_session), make_user(db_session, name="other")
    qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(mine))
    assert [c["title"] for c in qa.get("/qa/conversations", headers=auth(mine)).json()] == [
        QUESTION
    ]
    assert qa.get("/qa/conversations", headers=auth(other)).json() == []


def test_reopening_a_chat_redacts_answers_whose_sources_are_no_longer_allowed(db_session, qa):
    # The fake chunks are not in the database, which is what "no longer allowed" looks like.
    user = make_user(db_session)
    cid = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).json()[
        "conversation_id"
    ]
    messages = qa.get(f"/qa/conversations/{cid}", headers=auth(user)).json()
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == QUESTION and not messages[0]["redacted"]
    assert messages[1]["redacted"] is True
    assert messages[1]["content"] == service.REVOKED_TEXT
    assert messages[1]["citations"] == []


def test_reopening_a_chat_keeps_answers_whose_sources_are_still_allowed(db_session, qa):
    user = make_user(db_session)
    cid = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).json()[
        "conversation_id"
    ]
    views = service.get_messages(
        db_session, user, uuid.UUID(cid), check_access=lambda db, u, ids, purpose: set(ids)
    )
    assert views[1].redacted is False
    assert views[1].content == GOOD.answer
    assert views[1].citations[0]["quote"] == "monthly commitment of 99.95 percent"


def test_other_people_get_404_and_the_attempt_is_logged(db_session, qa):
    owner, other = make_user(db_session), make_user(db_session, name="other")
    cid = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(owner)).json()[
        "conversation_id"
    ]
    assert qa.get(f"/qa/conversations/{cid}", headers=auth(other)).status_code == 404
    assert qa.delete(f"/qa/conversations/{cid}", headers=auth(other)).status_code == 404
    again = {"question": "hello there", "conversation_id": cid}
    assert qa.post("/qa/ask", json=again, headers=auth(other)).status_code == 404
    assert len(events(db_session, "access_decision", other.id)) == 3
    kept = (
        select(func.count())
        .select_from(QaMessage)
        .where(QaMessage.conversation_id == uuid.UUID(cid))
    )
    assert db_session.scalar(kept) == 2


def test_deleting_a_chat_removes_it_and_is_audited(db_session, qa):
    user = make_user(db_session)
    cid = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).json()[
        "conversation_id"
    ]
    assert qa.delete(f"/qa/conversations/{cid}", headers=auth(user)).status_code == 204
    assert qa.get(f"/qa/conversations/{cid}", headers=auth(user)).status_code == 404
    left = (
        select(func.count())
        .select_from(QaMessage)
        .where(QaMessage.conversation_id == uuid.UUID(cid))
    )
    assert db_session.scalar(left) == 0
    assert events(db_session, "qa_conversation_deleted", user.id)[0].detail == {"messages": 2}


def test_if_the_model_is_down_nothing_is_saved(db_session, qa):
    user = make_user(db_session)
    before = count(db_session, QaConversation)
    qa.llm.fail = True
    response = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user))
    assert response.status_code == 503
    assert count(db_session, QaConversation) == before
    assert qa.get("/qa/conversations", headers=auth(user)).json() == []


def test_a_no_answer_is_saved_as_such(db_session, qa):
    user = make_user(db_session)
    qa.llm.answer = AnswerOut(can_answer=False, answer="", citations=[])
    body = qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).json()
    assert body["status"] == "no_answer"
    saved = db_session.scalars(
        select(QaMessage)
        .join(QaConversation)
        .where(QaConversation.user_id == user.id, QaMessage.role == "assistant")
    ).one()
    assert (saved.status, saved.content, saved.citations) == ("no_answer", NO_ANSWER_TEXT, [])


def test_questions_per_hour_are_limited_for_each_person(db_session, qa, monkeypatch):
    user = make_user(db_session)
    monkeypatch.setattr(service, "MAX_QUESTIONS_PER_HOUR", 1)
    assert qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).status_code == 200
    assert qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(user)).status_code == 429
    other = make_user(db_session, name="other")
    assert qa.post("/qa/ask", json={"question": QUESTION}, headers=auth(other)).status_code == 200
