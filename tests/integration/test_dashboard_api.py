import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.auth.tokens import create_access_token
from app.core.db import get_db
from app.models import User
from app.models.enums import Classification, Role
from app.rfp.assess import Assessment
from app.rfp.judge import Judgement, Reason, Status
from app.rfp.store import create_run, finish_run, review_result, save_assessment

pytestmark = pytest.mark.integration

NOTE = "Checked the policy myself."


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_user(db, role=Role.EMPLOYEE, name="dash"):
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@dashtest.test",
        password_hash="not-a-real-hash",
        role=role,
        clearance=Classification.INTERNAL,
    )
    db.add(user)
    db.flush()
    return user


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def assessment(rid, status):
    req = SimpleNamespace(id=rid, section="S", priority="mandatory", text=f"Text {rid}", page=1)
    if status is None:
        return Assessment(req, None, "llm_unavailable", 0, (), None)
    judgement = Judgement(status=status, rationale="r", citations=(), reason=Reason.OK)
    return Assessment(req, judgement, None, 1, (), "m")


def make_run(db, user, statuses, finish=True):
    run = create_run(db, user, "RFP-T", "t.pdf", len(statuses))
    for position, (rid, status) in enumerate(statuses.items(), start=1):
        save_assessment(db, run, position, assessment(rid, status))
    if finish:
        finish_run(db, user, run)
    return run


def test_overview_needs_a_login(client):
    assert client.get("/rfp/overview").status_code == 401
    assert client.get("/audit/recent").status_code == 401


def test_a_person_with_no_runs_sees_zeros(db_session, client):
    body = client.get("/rfp/overview", headers=auth(make_user(db_session))).json()
    assert body == {
        "runs_total": 0,
        "runs_running": 0,
        "answers_total": 0,
        "pending_review": 0,
        "reviewed": 0,
        "rejected": 0,
        "status_counts": {},
        "compliance_rate": None,
    }


def test_overview_counts_the_reviewers_choice_over_the_systems(db_session, client):
    user = make_user(db_session)
    run = make_run(
        db_session,
        user,
        {
            "T-001": Status.COMPLIANT,
            "T-002": Status.COMPLIANT,
            "T-003": Status.PARTIAL,
            "T-004": Status.COMPLIANT,
            "T-005": None,
        },
    )
    make_run(db_session, user, {"U-001": Status.INSUFFICIENT_EVIDENCE}, finish=False)
    review_result(db_session, user, run.id, "T-001", "approve")
    review_result(db_session, user, run.id, "T-002", "edit", "non_compliant", NOTE)
    review_result(db_session, user, run.id, "T-004", "reject", note=NOTE)

    body = client.get("/rfp/overview", headers=auth(user)).json()
    assert (body["runs_total"], body["runs_running"]) == (2, 1)
    assert body["answers_total"] == 6
    assert (body["reviewed"], body["rejected"], body["pending_review"]) == (2, 1, 3)
    assert body["status_counts"] == {
        "compliant": 1,
        "non_compliant": 1,
        "partial": 1,
        "not_judged": 1,
        "insufficient_evidence": 1,
    }
    assert body["compliance_rate"] == 25.0  # 1 compliant of 4 answers the system could judge


def test_overview_never_includes_other_peoples_runs(db_session, client):
    owner, other = make_user(db_session), make_user(db_session, name="other")
    make_run(db_session, owner, {"T-001": Status.COMPLIANT})
    body = client.get("/rfp/overview", headers=auth(other)).json()
    assert (body["runs_total"], body["answers_total"]) == (0, 0)


def test_people_see_only_their_own_activity_without_details(db_session, client):
    me, other = make_user(db_session), make_user(db_session, name="other")
    make_run(db_session, me, {"T-001": Status.COMPLIANT})
    make_run(db_session, other, {"X-001": Status.COMPLIANT})
    rows = client.get("/audit/recent", headers=auth(me)).json()
    assert rows and all(row["user_email"] is None and row["detail"] is None for row in rows)
    assert {row["action"] for row in rows} >= {"rfp_run_started", "rfp_run_finished"}
    emails = client.get("/audit/recent?limit=100", headers=auth(other)).json()
    assert all(row["user_email"] is None for row in emails)


def test_an_auditor_sees_everyones_activity_with_details(db_session, client):
    owner, auditor = make_user(db_session), make_user(db_session, Role.AUDITOR, "aud")
    make_run(db_session, owner, {"T-001": Status.COMPLIANT})
    rows = client.get("/audit/recent?limit=100", headers=auth(auditor)).json()
    mine = [row for row in rows if row["user_email"] == owner.email]
    assert mine and all(row["detail"] is not None for row in mine)


def test_the_limit_is_bounded(db_session, client):
    user = make_user(db_session)
    assert client.get("/audit/recent?limit=0", headers=auth(user)).status_code == 422
    assert client.get("/audit/recent?limit=101", headers=auth(user)).status_code == 422
