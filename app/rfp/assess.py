"""Run the judge for each requirement of an RFP, using only evidence the user may see.

Nothing here touches the database directly. The caller passes `search_fn`, which already carries
the database session, the logged-in user and the purpose, so the permission filter cannot be
skipped by accident. That is also what makes this module easy to test with fakes.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.llm.client import LLM, LLMUnavailable
from app.rfp.judge import Evidence, JudgeAnswer, Judgement, judge_requirement, make_evidence

if TYPE_CHECKING:
    from app.retrieval.search import SearchHit
    from app.rfp.parse import Requirement

MAX_EVIDENCE = 6  # excerpts shown to the model for one requirement
STOP_AFTER_FAILURES = 3  # model unavailable this many times in a row: stop calling it

ERR_LLM_UNAVAILABLE = "llm_unavailable"
ERR_FLAGGED = "flagged_for_human_review"
ERR_SKIPPED = "skipped_model_unavailable"

SearchFn = Callable[[str], "Sequence[SearchHit]"]


@dataclass(frozen=True)
class Assessment:
    requirement: Requirement
    judgement: Judgement | None  # None means "could not be judged", see `error`
    error: str | None
    evidence_count: int
    document_ids: tuple[uuid.UUID, ...]  # documents whose text the model was shown
    model: str | None


def hits_to_evidence(hits: Sequence[SearchHit], limit: int = MAX_EVIDENCE) -> list[Evidence]:
    return [
        make_evidence(
            index,
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            title=hit.filename,
            section=hit.section,
            page=hit.page,
            text=hit.content,
        )
        for index, hit in enumerate(hits[:limit], start=1)
    ]


class ModelAsk:
    """Turns an LLM into the `ask(system, prompt) -> JudgeAnswer` the judge expects."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm
        self.model: str | None = None

    def __call__(self, system: str, prompt: str) -> JudgeAnswer:
        result = self._llm.generate(system, prompt, JudgeAnswer)
        self.model = result.model
        return result.value


def assess_requirement(
    requirement: Requirement,
    search_fn: SearchFn,
    ask: ModelAsk | Callable[[str, str], JudgeAnswer],
    limit: int = MAX_EVIDENCE,
) -> Assessment:
    if requirement.flagged:
        # The requirement's own wording tried to steer the system. A person looks at it instead.
        return Assessment(requirement, None, ERR_FLAGGED, 0, (), None)

    evidence = hits_to_evidence(search_fn(requirement.text), limit)
    document_ids = tuple(dict.fromkeys(item.document_id for item in evidence))
    try:
        judgement = judge_requirement(requirement.text, requirement.priority, evidence, ask)
    except LLMUnavailable:
        return Assessment(requirement, None, ERR_LLM_UNAVAILABLE, len(evidence), document_ids, None)
    model = getattr(ask, "model", None) if evidence else None
    return Assessment(requirement, judgement, None, len(evidence), document_ids, model)


def assess_rfp(
    requirements: Sequence[Requirement],
    search_fn: SearchFn,
    ask: ModelAsk | Callable[[str, str], JudgeAnswer],
    on_result: Callable[[Assessment], None] | None = None,
    limit: int = MAX_EVIDENCE,
) -> list[Assessment]:
    """Assess every requirement in order. `on_result` is called after each one (audit, progress).

    If the model is unavailable several times in a row, the rest are marked as skipped instead of
    waiting through every retry again.
    """
    results: list[Assessment] = []
    failures = 0
    for requirement in requirements:
        if failures >= STOP_AFTER_FAILURES:
            outcome = Assessment(requirement, None, ERR_SKIPPED, 0, (), None)
        else:
            outcome = assess_requirement(requirement, search_fn, ask, limit)
            if outcome.error == ERR_LLM_UNAVAILABLE:
                failures += 1
            elif outcome.error is None:
                failures = 0
        results.append(outcome)
        if on_result is not None:
            on_result(outcome)
    return results
