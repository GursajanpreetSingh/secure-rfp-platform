import csv
import io
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import AuditEvent, User
from app.models.enums import Classification, Role
from app.rfp.assess import Assessment
from app.rfp.export import ExportBlocked, export_run_csv, safe_cell
from app.rfp.judge import Citation, Judgement, Reason, Status
from app.rfp.store import RunNotFound, create_run, finish_run, review_result, save_assessment

pytestmark = pytest.mark.integration

NOTE = "Checked the policy myself."


def make_user(db, name="owner"):
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@exporttest.test",
        password_hash="not-a-real-hash",
        role=Role.EMPLOYEE,
        clearance=Classification.INTERNAL,
    )
    db.add(user)
    db.flush()
    return user


def judged(rid, status=Status.COMPLIANT, text=None, quote="a real quote here"):
    doc, chunk = uuid.uuid4(), uuid.uuid4()
    judgement = Judgement(
        status=status,
        rationale="Because of the quote.",
        citations=(Citation("E1", chunk, doc, "DOC-001_policy.pdf", "Sec", 4, quote),),
        reason=Reason.OK,
    )
    req = SimpleNamespace(
        id=rid, section="Security", priority="mandatory", text=text or f"Text of {rid}", page=1
    )
    return Assessment(req, judgement, None, 1, (doc,), "fake-model")


def make_run(db, user, assessments, finish=True):
    run = create_run(db, user, "RFP-T", "t.pdf", len(assessments))
    for position, assessment in enumerate(assessments, start=1):
        save_assessment(db, run, position, assessment)
    if finish:
        finish_run(db, user, run)
    return run


def rows_of(data):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def test_pending_answers_block_the_export(db_session):
    user = make_user(db_session)
    run = make_run(db_session, user, [judged("T-001"), judged("T-002")])
    review_result(db_session, user, run.id, "T-001", "approve")
    with pytest.raises(ExportBlocked, match="1 answer"):
        export_run_csv(db_session, user, run.id)


def test_unfinished_empty_and_all_rejected_runs_are_blocked(db_session):
    user = make_user(db_session)
    unfinished = make_run(db_session, user, [judged("T-001")], finish=False)
    with pytest.raises(ExportBlocked):
        export_run_csv(db_session, user, unfinished.id)
    empty = make_run(db_session, user, [])
    with pytest.raises(ExportBlocked):
        export_run_csv(db_session, user, empty.id)
    rejected = make_run(db_session, user, [judged("T-001")])
    review_result(db_session, user, rejected.id, "T-001", "reject", note=NOTE)
    with pytest.raises(ExportBlocked, match="rejected"):
        export_run_csv(db_session, user, rejected.id)


def test_only_the_owner_can_export(db_session):
    owner, other = make_user(db_session), make_user(db_session, "other")
    run = make_run(db_session, owner, [judged("T-001")])
    review_result(db_session, owner, run.id, "T-001", "approve")
    with pytest.raises(RunNotFound):
        export_run_csv(db_session, other, run.id)


def test_reviewed_run_exports_approved_and_edited_but_not_rejected(db_session):
    user = make_user(db_session)
    run = make_run(
        db_session,
        user,
        [judged("T-001", Status.PARTIAL), judged("T-002"), judged("T-003")],
    )
    review_result(db_session, user, run.id, "T-001", "approve")
    review_result(db_session, user, run.id, "T-002", "edit", "non_compliant", NOTE)
    review_result(db_session, user, run.id, "T-003", "reject", note=NOTE)
    name, data = export_run_csv(db_session, user, run.id)
    assert name == "RFP-T_compliance_matrix.csv"
    table = rows_of(data)
    assert table[0][:2] == ["Requirement ID", "Section"]
    assert [row[0] for row in table[1:]] == ["T-001", "T-002"]
    assert table[1][4:6] == ["Partially compliant", "Approved as suggested"]
    assert table[2][4:6] == ["Non-compliant", "Status set by reviewer"]
    assert NOTE not in data.decode("utf-8-sig")


def test_evidence_the_user_can_no_longer_use_is_not_exported(db_session):
    # These chunk ids do not exist, which is the same as "no longer allowed" to the export.
    user = make_user(db_session)
    run = make_run(db_session, user, [judged("T-001", quote="secret words nobody may export")])
    review_result(db_session, user, run.id, "T-001", "approve")
    _, data = export_run_csv(db_session, user, run.id)
    text = data.decode("utf-8-sig")
    assert "secret words" not in text
    assert "[source no longer available to you]" in text
    audit = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "rfp_exported", AuditEvent.user_id == user.id)
    ).one()
    assert audit.detail["rows"] == 1
    assert audit.detail["evidence_redacted"] == 1


def test_cells_cannot_start_a_formula(db_session):
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell("-2+3") == "'-2+3"
    assert safe_cell("plain") == "plain"
    assert safe_cell(None) == ""
    user = make_user(db_session)
    run = make_run(db_session, user, [judged("T-001", text='=HYPERLINK("http://x","y")')])
    review_result(db_session, user, run.id, "T-001", "approve")
    _, data = export_run_csv(db_session, user, run.id)
    assert rows_of(data)[1][3].startswith("'=")
