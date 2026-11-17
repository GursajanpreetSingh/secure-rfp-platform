import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.routes import rfp as rfp_routes
from app.auth.deps import get_current_user
from app.auth.policy_types import Subject
from app.core.db import get_db
from app.models import User
from app.models.enums import Purpose
from app.qa import service
from app.qa.answer import Answer
from app.qa.schemas import (
    AnswerOut,
    AskIn,
    ChatAnswerOut,
    ConversationOut,
    MessageOut,
    PublicAskIn,
    SourceOut,
)
from app.retrieval.search import search
from app.rfp.export import subject_of

router = APIRouter(prefix="/qa", tags=["qa"])


@dataclass
class Backend:
    llm: object
    make_search: Callable[[Session, Subject], Callable]


def get_backend() -> Backend:
    """The real model and search. Tests replace this."""
    try:
        llm, embedder = rfp_routes._llm(), rfp_routes._embedder()
    except ValueError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "the assistant is not set up"
        ) from None

    def make_search(db: Session, subject: Subject):
        def search_fn(question: str):
            return search(
                db,
                subject,
                question,
                Purpose.ENTERPRISE_QA,
                embedder,
                top_k=service.EVIDENCE_LIMIT,
            )

        return search_fn

    return Backend(llm=llm, make_search=make_search)


def _sources(answer: Answer) -> list[SourceOut]:
    return [
        SourceOut(title=c.title, section=c.section, page=c.page, quote=c.quote)
        for c in answer.citations
    ]


def _problem(db: Session, error: Exception) -> HTTPException:
    """Turn a service error into an HTTP error. Audit rows written so far are kept."""
    db.commit()
    if isinstance(error, service.QuestionRejected):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error))
    if isinstance(error, service.RateLimited):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error))
    if isinstance(error, service.AssistantBusy):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    return HTTPException(status.HTTP_404_NOT_FOUND, "no such conversation")


_EXPECTED = (
    service.QuestionRejected,
    service.RateLimited,
    service.AssistantBusy,
    service.ConversationNotFound,
)


@router.post("/public/ask", response_model=AnswerOut)
def ask_public(
    body: PublicAskIn,
    response: Response,
    db: Session = Depends(get_db),
    backend: Backend = Depends(get_backend),
):
    """No login. Answers only from documents open to the public. Nothing is saved."""
    response.headers["Cache-Control"] = "no-store"
    try:
        answer = service.ask_public(
            db, body.question, backend.llm, backend.make_search(db, service.GUEST)
        )
    except _EXPECTED as error:
        raise _problem(db, error) from None
    db.commit()
    return AnswerOut(status=answer.status.value, text=answer.text, sources=_sources(answer))


@router.post("/ask", response_model=ChatAnswerOut)
def ask(
    body: AskIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    backend: Backend = Depends(get_backend),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        reply = service.ask_in_chat(
            db,
            user,
            body.question,
            body.conversation_id,
            backend.llm,
            backend.make_search(db, subject_of(user)),
        )
    except _EXPECTED as error:
        raise _problem(db, error) from None
    db.commit()
    return ChatAnswerOut(
        status=reply.answer.status.value,
        text=reply.answer.text,
        sources=_sources(reply.answer),
        conversation_id=reply.conversation_id,
        title=reply.title,
    )


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.list_conversations(db, user)


@router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
def conversation(
    conversation_id: uuid.UUID,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        views = service.get_messages(db, user, conversation_id)
    except _EXPECTED as error:
        raise _problem(db, error) from None
    return [MessageOut(**view.__dict__) for view in views]


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service.delete_conversation(db, user, conversation_id)
    except _EXPECTED as error:
        raise _problem(db, error) from None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
