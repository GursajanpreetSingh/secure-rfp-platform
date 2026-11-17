import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.qa.answer import MAX_QUESTION_CHARS


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=MAX_QUESTION_CHARS * 2)
    conversation_id: uuid.UUID | None = None


class PublicAskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(max_length=MAX_QUESTION_CHARS * 2)


class SourceOut(BaseModel):
    title: str
    section: str | None
    page: int | None
    quote: str


class AnswerOut(BaseModel):
    status: str
    text: str
    sources: list[SourceOut]


class ChatAnswerOut(AnswerOut):
    conversation_id: uuid.UUID
    title: str


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    updated_at: datetime


class MessageOut(BaseModel):
    position: int
    role: str
    content: str
    status: str
    citations: list[dict]
    created_at: datetime
    redacted: bool
