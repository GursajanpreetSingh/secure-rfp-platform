import uuid
from types import SimpleNamespace

from app.llm.client import LLMResult, LLMUnavailable
from app.rfp.assess import (
    ERR_FLAGGED,
    ERR_LLM_UNAVAILABLE,
    ERR_SKIPPED,
    MAX_EVIDENCE,
    STOP_AFTER_FAILURES,
    ModelAsk,
    assess_requirement,
    assess_rfp,
    hits_to_evidence,
    requirement_query,
)
from app.rfp.judge import JudgeAnswer, Reason, Status

TEXT = "Production uptime is covered by a monthly commitment of 99.95 percent."


def hit(text=TEXT, doc=None):
    return SimpleNamespace(
        chunk_id=uuid.uuid4(),
        document_id=doc or uuid.uuid4(),
        filename="DOC-005_support_policy_and_sla.pdf",
        section="SLA",
        page=3,
        content=text,
    )


def req(rid="A-001", flagged=False):
    return SimpleNamespace(id=rid, text="Uptime of 99.9%.", priority="mandatory", flagged=flagged)


class FakeLLM:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, 0

    def generate(self, system, prompt, schema):
        self.calls += 1
        if self.fail:
            raise LLMUnavailable("busy")
        return LLMResult(value=self.answer, model="fake-model", tokens=10)


def good_answer():
    return JudgeAnswer(
        status="compliant",
        rationale="Meets it.",
        citations=[{"ref": "E1", "quote": "monthly commitment of 99.95 percent"}],
    )


def test_hits_become_numbered_evidence_and_are_capped():
    hits = [hit() for _ in range(MAX_EVIDENCE + 3)]
    evidence = hits_to_evidence(hits)
    assert [e.ref for e in evidence] == [f"E{i}" for i in range(1, MAX_EVIDENCE + 1)]
    assert evidence[0].title == "DOC-005_support_policy_and_sla.pdf"
    assert evidence[0].chunk_id == hits[0].chunk_id


def test_assessment_records_model_documents_and_verified_status():
    h = hit()
    ask = ModelAsk(FakeLLM(good_answer()))
    result = assess_requirement(req(), lambda q: [h], ask)
    assert result.error is None
    assert result.judgement.status is Status.COMPLIANT
    assert result.document_ids == (h.document_id,)
    assert result.model == "fake-model"
    assert result.evidence_count == 1


def test_search_receives_the_requirement_text():
    seen = []
    ask = ModelAsk(FakeLLM(good_answer()))
    assess_requirement(req(), lambda q: seen.append(q) or [hit()], ask)
    assert seen == ["Uptime of 99.9%"]


def test_no_hits_means_no_model_call():
    llm = FakeLLM(good_answer())
    result = assess_requirement(req(), lambda q: [], ModelAsk(llm))
    assert llm.calls == 0
    assert result.judgement.status is Status.INSUFFICIENT_EVIDENCE
    assert result.judgement.reason is Reason.NO_EVIDENCE
    assert result.model is None


def test_flagged_requirement_is_not_searched_or_judged():
    llm = FakeLLM(good_answer())

    def boom(q):
        raise AssertionError("search must not run")

    result = assess_requirement(req(flagged=True), boom, ModelAsk(llm))
    assert result.judgement is None
    assert result.error == ERR_FLAGGED
    assert llm.calls == 0


def test_model_outage_is_reported_not_turned_into_a_status():
    result = assess_requirement(req(), lambda q: [hit()], ModelAsk(FakeLLM(fail=True)))
    assert result.judgement is None
    assert result.error == ERR_LLM_UNAVAILABLE
    assert result.evidence_count == 1


def test_fabricated_quote_is_downgraded_end_to_end():
    bad = JudgeAnswer(
        status="compliant",
        rationale="x",
        citations=[{"ref": "E1", "quote": "we promise one hundred percent uptime always"}],
    )
    result = assess_requirement(req(), lambda q: [hit()], ModelAsk(FakeLLM(bad)))
    assert result.judgement.status is Status.INSUFFICIENT_EVIDENCE
    assert result.judgement.downgraded_from is Status.COMPLIANT


def test_rfp_run_keeps_order_and_calls_back_for_each():
    seen = []
    reqs = [req("A-001"), req("A-002"), req("A-003")]
    out = assess_rfp(reqs, lambda q: [hit()], ModelAsk(FakeLLM(good_answer())), seen.append)
    assert [a.requirement.id for a in out] == ["A-001", "A-002", "A-003"]
    assert seen == out


def test_run_stops_calling_a_model_that_keeps_failing():
    llm = FakeLLM(fail=True)
    reqs = [req(f"A-{i:03d}") for i in range(STOP_AFTER_FAILURES + 4)]
    out = assess_rfp(reqs, lambda q: [hit()], ModelAsk(llm))
    assert llm.calls == STOP_AFTER_FAILURES
    assert [a.error for a in out[:STOP_AFTER_FAILURES]] == [ERR_LLM_UNAVAILABLE] * 3
    assert all(a.error == ERR_SKIPPED for a in out[STOP_AFTER_FAILURES:])


def test_success_resets_the_failure_count():
    answers = iter([True, True, False, True, True, False])  # True = fail

    class Flaky(FakeLLM):
        def generate(self, system, prompt, schema):
            self.fail = next(answers)
            return super().generate(system, prompt, schema)

    out = assess_rfp(
        [req(f"A-{i:03d}") for i in range(6)], lambda q: [hit()], ModelAsk(Flaky(good_answer()))
    )
    assert not any(a.error == ERR_SKIPPED for a in out)


def test_evidence_limit_can_be_changed():
    seen = []
    ask = ModelAsk(FakeLLM(good_answer()))
    out = assess_requirement(req(), lambda q: [hit() for _ in range(10)], ask, limit=8)
    assert out.evidence_count == 8
    out = assess_rfp([req()], lambda q: seen.append(q) or [hit() for _ in range(10)], ask, limit=3)
    assert out[0].evidence_count == 3


def test_query_drops_the_opening_boilerplate():
    cases = {
        "The vendor shall employ at least 200 people.": "employ at least 200 people",
        "The solution shall support at least 6,000 concurrent users.": (
            "support at least 6,000 concurrent users"
        ),
        "The proposed platform must also be able to export audit logs.": "export audit logs",
        "A supplier will provide staff training.": "provide staff training",
    }
    for original, expected in cases.items():
        assert requirement_query(original) == expected


def test_query_keeps_requirements_without_that_opening():
    text = "All data in transit shall be protected with TLS 1.2 or higher."
    assert requirement_query(text) == text.rstrip(".")
    assert requirement_query("Customer tenants shall be isolated.") == (
        "Customer tenants shall be isolated"
    )


def test_query_never_becomes_too_short_to_search_with():
    assert requirement_query("The vendor shall comply.") == "The vendor shall comply."
