"""Question answering for two kinds of asker.

Logged in: the answer is found with that person's own permissions, and the chat is saved so
they can come back to it. Public: no account, answers come only from what an outsider with
public clearance may see, and NOTHING is saved. Both write a metadata-only audit event: ids,
counts and statuses, never the question or the answer.

When a saved chat is opened again, every answer's sources are checked against the access rules
as they are now. If a source is no longer allowed, that answer is replaced by a notice.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import AuditAction, record_event
from app.auth.policy_types import Subject
from app.llm.client import LLMUnavailable
from app.models import AuditEvent, QaConversation, QaMessage, User
from app.models.enums import AuditDecision, Classification, Purpose, Role
from app.qa.answer import (
    MAX_QUESTION_CHARS,
    Answer,
    AnswerOut,
    AnswerStatus,
    Turn,
    answer_question,
    search_text,
)
from app.rfp.assess import hits_to_evidence
from app.rfp.export import visible_chunk_ids
from app.rfp.store import citation_to_json

if TYPE_CHECKING:
    from app.rfp.assess import SearchFn

MAX_QUESTIONS_PER_HOUR = 30  # per logged-in person
MAX_PUBLIC_QUESTIONS_PER_HOUR = 60  # for all anonymous visitors together
EVIDENCE_LIMIT = 6
TITLE_CHARS = 60
REVOKED_TEXT = "[This answer used a document you can no longer access.]"

# The anonymous visitor: an outsider with public clearance and no identity of their own.
GUEST = Subject(
    id=uuid.UUID(int=0),
    role=Role.EXTERNAL,
    department=None,
    clearance=Classification.PUBLIC,
    is_active=True,
)


class QuestionRejected(ValueError):
    """The question is empty, too long or unusable. The message is safe to show."""


class RateLimited(RuntimeError):
    pass


class ConversationNotFound(LookupError):
    pass


class AssistantBusy(RuntimeError):
    """The language model could not be reached. Nothing was saved."""


class QaAsk:
    """Turns an LLM into `ask(system, prompt) -> AnswerOut`, remembering the model's name."""

    def __init__(self, llm) -> None:
        self._llm = llm
        self.model: str | None = None

    def __call__(self, system: str, prompt: str) -> AnswerOut:
        result = self._llm.generate(system, prompt, AnswerOut)
        self.model = result.model
        return result.value


@dataclass(frozen=True)
class ChatReply:
    conversation_id: uuid.UUID
    title: str
    answer: Answer
    model: str | None


@dataclass(frozen=True)
class MessageView:
    position: int
    role: str
    content: str
    status: str
    citations: list[dict]
    created_at: datetime
    redacted: bool


def clean_question(question: str) -> str:
    question = " ".join(question.split())
    if not question:
        raise QuestionRejected("Type a question first.")
    if len(question) > MAX_QUESTION_CHARS:
        raise QuestionRejected(f"Keep the question under {MAX_QUESTION_CHARS} characters.")
    return question


def _hour_ago() -> datetime:
    return datetime.now(UTC) - timedelta(hours=1)


def _run_model(
    question: str, history: list[Turn], search_fn: SearchFn, llm
) -> tuple[Answer, list, str | None]:
    hits = search_fn(search_text(question, history))
    evidence = hits_to_evidence(hits, EVIDENCE_LIMIT)
    ask = QaAsk(llm)
    try:
        answer = answer_question(question, history, evidence, ask)
    except LLMUnavailable:
        raise AssistantBusy("The assistant is busy. Please try again in a moment.") from None
    return answer, evidence, ask.model if evidence else None


def _audit(
    db: Session,
    user: User | None,
    answer: Answer,
    evidence: list,
    question: str,
    model: str | None,
    resource_type: str,
    resource_id: uuid.UUID | None,
    request_id: str | None,
) -> None:
    record_event(
        db,
        AuditAction.QA_ASKED,
        AuditDecision.INFO,
        user=user,
        resource_type=resource_type,
        resource_id=resource_id,
        purpose=Purpose.ENTERPRISE_QA,
        detail={
            "status": answer.status.value,
            "why": answer.why.value,
            "evidence_count": len(evidence),
            "documents_shown": list(dict.fromkeys(str(e.document_id) for e in evidence)),
            "documents_cited": list(dict.fromkeys(str(c.document_id) for c in answer.citations)),
            "question_length": len(question),
            "model": model,
        },
        request_id=request_id,
    )


# --- public ---------------------------------------------------------------------------------


def ask_public(
    db: Session, question: str, llm, search_fn: SearchFn, request_id: str | None = None
) -> Answer:
    """Answer an anonymous visitor. Nothing but an audit row is written."""
    question = clean_question(question)
    recent = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == AuditAction.QA_ASKED.value,
            AuditEvent.user_id.is_(None),
            AuditEvent.occurred_at > _hour_ago(),
        )
    )
    if recent >= MAX_PUBLIC_QUESTIONS_PER_HOUR:
        raise RateLimited("Too many questions right now. Please try again later.")
    answer, evidence, model = _run_model(question, [], search_fn, llm)
    _audit(db, None, answer, evidence, question, model, "qa_public", None, request_id)
    return answer


# --- logged in ------------------------------------------------------------------------------


def _owned_conversation(
    db: Session, user: User, conversation_id: uuid.UUID, request_id: str | None = None
) -> QaConversation:
    conversation = db.get(QaConversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        record_event(
            db,
            AuditAction.ACCESS_DECISION,
            AuditDecision.DENY,
            user=user,
            resource_type="qa_conversation",
            resource_id=conversation_id,
            purpose=Purpose.ENTERPRISE_QA,
            detail={"reason": "not_owner_or_missing"},
            request_id=request_id,
        )
        raise ConversationNotFound("no such conversation")
    return conversation


def _history(db: Session, conversation: QaConversation) -> tuple[list[Turn], int]:
    rows = db.scalars(
        select(QaMessage)
        .where(QaMessage.conversation_id == conversation.id)
        .order_by(QaMessage.position)
    ).all()
    return [Turn(r.role, r.content) for r in rows], len(rows)


def ask_in_chat(
    db: Session,
    user: User,
    question: str,
    conversation_id: uuid.UUID | None,
    llm,
    search_fn: SearchFn,
    request_id: str | None = None,
) -> ChatReply:
    """Answer a logged-in person and save both sides. If the model is down, save nothing."""
    question = clean_question(question)
    asked = db.scalar(
        select(func.count())
        .select_from(QaMessage)
        .join(QaConversation, QaConversation.id == QaMessage.conversation_id)
        .where(
            QaConversation.user_id == user.id,
            QaMessage.role == "user",
            QaMessage.created_at > _hour_ago(),
        )
    )
    if asked >= MAX_QUESTIONS_PER_HOUR:
        raise RateLimited("You have asked a lot of questions. Please try again in a while.")

    if conversation_id is None:
        conversation, turns, count = None, [], 0
    else:
        conversation = _owned_conversation(db, user, conversation_id, request_id)
        turns, count = _history(db, conversation)

    answer, evidence, model = _run_model(question, turns, search_fn, llm)

    if conversation is None:
        conversation = QaConversation(user_id=user.id, title=question[:TITLE_CHARS])
        db.add(conversation)
        db.flush()
    db.add(
        QaMessage(
            conversation_id=conversation.id,
            position=count + 1,
            role="user",
            content=question,
            status="asked",
        )
    )
    db.add(
        QaMessage(
            conversation_id=conversation.id,
            position=count + 2,
            role="assistant",
            content=answer.text,
            status=answer.status.value,
            citations=[citation_to_json(c) for c in answer.citations],
            model=model,
        )
    )
    conversation.updated_at = func.now()
    db.flush()
    _audit(
        db, user, answer, evidence, question, model, "qa_conversation", conversation.id, request_id
    )
    return ChatReply(conversation.id, conversation.title, answer, model)


def list_conversations(db: Session, user: User) -> list[QaConversation]:
    return list(
        db.scalars(
            select(QaConversation)
            .where(QaConversation.user_id == user.id)
            .order_by(QaConversation.updated_at.desc())
        ).all()
    )


def get_messages(
    db: Session,
    user: User,
    conversation_id: uuid.UUID,
    request_id: str | None = None,
    check_access: Callable = visible_chunk_ids,
) -> list[MessageView]:
    """The saved messages, with any answer whose sources are no longer allowed replaced."""
    conversation = _owned_conversation(db, user, conversation_id, request_id)
    rows = db.scalars(
        select(QaMessage)
        .where(QaMessage.conversation_id == conversation.id)
        .order_by(QaMessage.position)
    ).all()
    cited = sorted({c["chunk_id"] for r in rows for c in r.citations})
    visible = check_access(db, user, cited, purpose=Purpose.ENTERPRISE_QA)

    views = []
    for row in rows:
        revoked = any(c["chunk_id"] not in visible for c in row.citations)
        views.append(
            MessageView(
                position=row.position,
                role=row.role,
                content=REVOKED_TEXT if revoked else row.content,
                status=row.status,
                citations=[] if revoked else row.citations,
                created_at=row.created_at,
                redacted=revoked,
            )
        )
    return views


def delete_conversation(
    db: Session, user: User, conversation_id: uuid.UUID, request_id: str | None = None
) -> None:
    conversation = _owned_conversation(db, user, conversation_id, request_id)
    count = db.scalar(
        select(func.count())
        .select_from(QaMessage)
        .where(QaMessage.conversation_id == conversation.id)
    )
    db.delete(conversation)
    db.flush()
    record_event(
        db,
        AuditAction.QA_CONVERSATION_DELETED,
        AuditDecision.INFO,
        user=user,
        resource_type="qa_conversation",
        resource_id=conversation_id,
        purpose=Purpose.ENTERPRISE_QA,
        detail={"messages": count},
        request_id=request_id,
    )


__all__ = [
    "GUEST",
    "AnswerStatus",
    "AssistantBusy",
    "ChatReply",
    "ConversationNotFound",
    "MessageView",
    "QaAsk",
    "QuestionRejected",
    "RateLimited",
    "ask_in_chat",
    "ask_public",
    "clean_question",
    "delete_conversation",
    "get_messages",
    "list_conversations",
]
