import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditEvent, User
from app.models.enums import Classification, Role
from app.rfp.assess import Assessment
from app.rfp.judge import Citation, Judgement, Reason, Status
from app.rfp.store import (
    ReviewError,
    RunNotFound,
    create_run,
    finish_run,
    get_run,
    list_results,
    review_result,
    run_summary,
    save_assessment,
)

pytestmark = pytest.mark.integration

NOTE = "Checked the policy myself."


def make_user(db, name="owner"):
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@storetest.test",
        password_hash="not-a-real-hash",
        role=Role.EMPLOYEE,
        clearance=Classification.INTERNAL,
    )
    db.add(user)
    db.flush()
    return user


def requirement(rid):
    return SimpleNamespace(
        id=rid, section="Security", priority="mandatory", text=f"Text of {rid}", page=2
    )


def judged(rid, status=Status.COMPLIANT):
    doc, chunk = uuid.uuid4(), uuid.uuid4()
    judgement = Judgement(
        status=status,
        rationale="Because of the quote.",
        citations=(Citation("E1", chunk, doc, "DOC-001_x.pdf", "Sec", 4, "a real quote here"),),
        reason=Reason.OK,
    )
    return Assessment(requirement(rid), judgement, None, 3, (doc,), "fake-model")


def not_judged(rid):
    return Assessment(requirement(rid), None, "llm_unavailable", 2, (), None)


def finished_run(db, user, assessments):
    run = create_run(db, user, "RFP-T", "t.pdf", len(assessments))
    for position, assessment in enumerate(assessments, start=1):
        save_assessment(db, run, position, assessment)
    finish_run(db, user, run)
    return run


def events(db, action, user):
    return db.scalars(
        select(AuditEvent).where(AuditEvent.action == action, AuditEvent.user_id == user.id)
    ).all()


def test_saved_answers_keep_the_systems_words_and_start_pending(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001"), not_judged("T-002")])
    first, second = list_results(db_session, user, run.id)
    assert (first.requirement_id, first.ai_status, first.review_state) == (
        "T-001",
        "compliant",
        "pending",
    )
    assert first.citations[0]["quote"] == "a real quote here"
    assert first.model == "fake-model"
    assert (second.ai_status, second.ai_reason) == ("not_judged", "llm_unavailable")
    assert second.citations == []
    assert run.state == "completed"
    assert run.finished_at is not None


def test_run_start_and_finish_are_audited(db_session):
    user = make_user(db_session)
    finished_run(db_session, user, [judged("T-001")])
    assert len(events(db_session, "rfp_run_started", user)) == 1
    finish = events(db_session, "rfp_run_finished", user)[0]
    assert finish.detail["results"] == {"compliant": 1}


def test_only_the_owner_can_read_a_run_and_a_refusal_is_logged(db_session):
    owner, other = make_user(db_session), make_user(db_session, "other")
    run = finished_run(db_session, owner, [judged("T-001")])
    with pytest.raises(RunNotFound):
        get_run(db_session, other, run.id)
    with pytest.raises(RunNotFound):
        list_results(db_session, other, run.id)
    with pytest.raises(RunNotFound):
        review_result(db_session, other, run.id, "T-001", "approve")
    denied = events(db_session, "access_decision", other)
    assert len(denied) == 3
    assert denied[0].detail == {"reason": "not_owner_or_missing"}


def test_missing_run_looks_the_same_as_someone_elses(db_session):
    user = make_user(db_session)
    with pytest.raises(RunNotFound):
        get_run(db_session, user, uuid.uuid4())


def test_approve_keeps_the_systems_status(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001", Status.PARTIAL)])
    result = review_result(db_session, user, run.id, "T-001", "approve")
    assert (result.review_state, result.final_status) == ("approved", "partial")
    assert result.ai_status == "partial"
    assert result.reviewed_by == user.id
    assert result.reviewed_at is not None


def test_edit_replaces_the_final_status_but_not_the_systems_answer(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001", Status.PARTIAL)])
    result = review_result(
        db_session, user, run.id, "T-001", "edit", final_status="compliant", note=NOTE
    )
    assert (result.review_state, result.final_status) == ("edited", "compliant")
    assert result.ai_status == "partial"
    assert result.reviewer_note == NOTE


def test_edit_needs_a_real_status_and_a_note(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001")])
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "edit", "compliant", "short")
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "edit", "not_judged", NOTE)
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "edit", None, NOTE)


def test_approve_cannot_smuggle_in_a_different_status(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001", Status.PARTIAL)])
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "approve", final_status="compliant")


def test_an_answer_the_system_could_not_give_cannot_be_approved(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [not_judged("T-001")])
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "approve")
    fixed = review_result(
        db_session, user, run.id, "T-001", "edit", final_status="partial", note=NOTE
    )
    assert fixed.final_status == "partial"


def test_reject_needs_a_note_and_leaves_no_final_status(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001")])
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "reject")
    result = review_result(db_session, user, run.id, "T-001", "reject", note=NOTE)
    assert (result.review_state, result.final_status) == ("rejected", None)


def test_unknown_requirement_or_action_or_unfinished_run(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001")])
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-999", "approve")
    with pytest.raises(ReviewError):
        review_result(db_session, user, run.id, "T-001", "bless")
    open_run = create_run(db_session, user, "RFP-U", "u.pdf", 1)
    save_assessment(db_session, open_run, 1, judged("U-001"))
    with pytest.raises(ReviewError):
        review_result(db_session, user, open_run.id, "U-001", "approve")


def test_every_review_is_audited_without_the_note_text(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001")])
    review_result(db_session, user, run.id, "T-001", "edit", "non_compliant", NOTE)
    review_result(db_session, user, run.id, "T-001", "approve")
    logged = events(db_session, "rfp_review", user)
    assert len(logged) == 2
    first = min(logged, key=lambda e: e.id)
    assert first.detail["action"] == "edit"
    assert first.detail["final_status"] == "non_compliant"
    assert first.detail["previous_state"] == "pending"
    assert first.detail["note_length"] == len(NOTE)
    assert NOTE not in str(first.detail)


def test_summary_counts_and_export_readiness(db_session):
    user = make_user(db_session)
    run = finished_run(db_session, user, [judged("T-001"), judged("T-002"), not_judged("T-003")])
    summary = run_summary(db_session, user, run.id)
    assert summary["total"] == 3
    assert summary["pending"] == 3
    assert summary["ready_to_export"] is False
    review_result(db_session, user, run.id, "T-001", "approve")
    review_result(db_session, user, run.id, "T-002", "reject", note=NOTE)
    review_result(db_session, user, run.id, "T-003", "edit", "insufficient_evidence", NOTE)
    summary = run_summary(db_session, user, run.id)
    assert summary["pending"] == 0
    assert summary["ready_to_export"] is True
    assert summary["review_state"] == {"pending": 0, "approved": 1, "edited": 1, "rejected": 1}
