import pytest
from sqlalchemy.exc import IntegrityError

from app.models import RfpResult, RfpRun, User
from app.models.enums import Classification, Role

pytestmark = pytest.mark.integration


def make_user(db):
    user = User(
        email="rfp-models@modeltest.test",
        password_hash="not-a-real-hash",
        role=Role.EMPLOYEE,
        clearance=Classification.INTERNAL,
    )
    db.add(user)
    db.flush()
    return user


def make_run(db, user):
    run = RfpRun(created_by=user.id, rfp_name="RFP-T", source_filename="t.pdf")
    db.add(run)
    db.flush()
    return run


def make_result(run, requirement_id="T-001", **overrides):
    values = {
        "run_id": run.id,
        "position": 1,
        "requirement_id": requirement_id,
        "priority": "mandatory",
        "requirement_text": "The vendor shall do a thing.",
        "ai_status": "insufficient_evidence",
    }
    values.update(overrides)
    return RfpResult(**values)


def test_defaults_start_pending_and_unreviewed(db_session):
    run = make_run(db_session, make_user(db_session))
    assert run.state == "running"
    assert run.purpose == "rfp"
    result = make_result(run)
    db_session.add(result)
    db_session.flush()
    assert result.review_state == "pending"
    assert result.final_status is None
    assert result.reviewed_by is None
    assert result.citations == []


def test_one_answer_per_requirement_in_a_run(db_session):
    run = make_run(db_session, make_user(db_session))
    db_session.add(make_result(run))
    db_session.flush()
    db_session.add(make_result(run, position=2))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "field, value",
    [
        ("ai_status", "mostly_compliant"),
        ("review_state", "maybe"),
        ("final_status", "not_judged"),
    ],
)
def test_database_rejects_unknown_statuses(db_session, field, value):
    run = make_run(db_session, make_user(db_session))
    db_session.add(make_result(run, **{field: value}))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_unknown_run_state_is_rejected(db_session):
    user = make_user(db_session)
    db_session.add(RfpRun(created_by=user.id, rfp_name="X", source_filename="x.pdf", state="done"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_run_removes_its_results(db_session):
    run = make_run(db_session, make_user(db_session))
    result = make_result(run)
    db_session.add(result)
    db_session.flush()
    result_id = result.id
    db_session.delete(run)
    db_session.flush()
    db_session.expire_all()
    assert db_session.get(RfpResult, result_id) is None
