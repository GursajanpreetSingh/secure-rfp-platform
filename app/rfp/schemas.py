import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FinalStatus = Literal["compliant", "partial", "non_compliant", "insufficient_evidence"]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rfp_name: str
    source_filename: str
    state: str
    requirement_count: int
    created_at: datetime
    finished_at: datetime | None
    warnings: list[str]


class RunDetail(RunOut):
    answered: int
    summary: dict


class ResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requirement_id: str
    position: int
    section: str | None
    priority: str
    requirement_text: str
    page: int | None
    ai_status: str
    ai_reason: str | None
    ai_rationale: str
    downgraded_from: str | None
    citations: list[dict]
    review_state: str
    final_status: str | None
    reviewer_note: str | None
    reviewed_at: datetime | None


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "edit", "reject"]
    final_status: FinalStatus | None = None
    note: str | None = Field(default=None, max_length=2000)
