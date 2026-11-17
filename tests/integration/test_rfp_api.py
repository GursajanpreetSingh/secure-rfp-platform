import csv
import io
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.api.routes import rfp as rfp_routes
from app.auth.tokens import create_access_token
from app.core.db import get_db
from app.models import AuditEvent, RfpRun, User
from app.models.enums import Classification, Role
from app.rfp.judge import JudgeAnswer
from app.rfp.pipeline import NoRequirements, execute_run

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4 pretend"
NOTE = "I checked the policy myself."


def requirement(rid):
    return SimpleNamespace(
        id=rid,
        section="Security",
        priority="mandatory",
        text=f"The vendor shall do thing {rid}.",
        page=1,
        flagged=False,
    )


def fake_hit():
    return SimpleNamespace(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="DOC-001_security.pdf",
        section="Crypto",
        page=3,
        content="Encryption of data at rest uses AES-256 for every customer database.",
    )


def fake_ask(system, prompt):
    return JudgeAnswer(
        status="compliant",
        rationale="Stated in the policy.",
        citations=[{"ref": "E1", "quote": "uses AES-256 for every customer database"}],
    )


@pytest.fixture
def api(db_session, monkeypatch):
    monkeypatch.setattr(
        rfp_routes,
        "read_rfp",
        lambda path: SimpleNamespace(
            requirements=[requirement("T-001"), requirement("T-002")], suspicious=[], warnings=[]
        ),
    )

    def executor(factory, user_id, run_id, requirements, request_id):
        user, run = db_session.get(User, user_id), db_session.get(RfpRun, run_id)
        execute_run(db_session, user, run, requirements, lambda q: [fake_hit()], fake_ask)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[rfp_routes.get_executor] = lambda: executor
    app.dependency_overrides[rfp_routes.get_session_factory] = lambda: lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_user(db, role=Role.EMPLOYEE, name="emp"):
    user = User(
        email=f"{name}-{uuid.uuid4().hex[:8]}@apitest.test",
        password_hash="not-a-real-hash",
        role=role,
        department="sales",
        clearance=Classification.INTERNAL,
    )
    db.add(user)
    db.flush()
    return user


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def upload(client, user, name="RFP-T_demo.pdf", body=PDF):
    headers = {**auth(user), "X-Filename": name}
    return client.post("/rfp/runs", content=body, headers=headers)


def test_everything_needs_a_login(api):
    assert api.post("/rfp/runs", content=PDF).status_code == 401
    assert api.get("/rfp/runs").status_code == 401
    assert api.get(f"/rfp/runs/{uuid.uuid4()}/export").status_code == 401


def test_only_staff_roles_can_start_a_run_and_the_refusal_is_audited(db_session, api):
    outsider = make_user(db_session, Role.EXTERNAL, "ext")
    assert upload(api, outsider).status_code == 403
    logged = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "access_decision", AuditEvent.user_id == outsider.id
        )
    ).all()
    assert [e.detail["reason"] for e in logged] == ["role_not_allowed"]


def test_bad_uploads_are_refused(db_session, api, monkeypatch):
    user = make_user(db_session)
    assert upload(api, user, name="notes.exe").status_code == 415
    assert upload(api, user, body=b"not a pdf at all").status_code == 415
    assert upload(api, user, body=b"").status_code == 415
    monkeypatch.setattr(rfp_routes, "MAX_UPLOAD_BYTES", 10)
    assert upload(api, user, body=PDF + b"x" * 50).status_code == 413


def test_a_file_without_requirements_is_refused(db_session, api, monkeypatch):
    def none(path):
        raise NoRequirements("none")

    monkeypatch.setattr(rfp_routes, "read_rfp", none)
    assert upload(api, make_user(db_session)).status_code == 422


def test_upload_starts_a_run_that_completes_and_can_be_read_back(db_session, api):
    user = make_user(db_session)
    response = upload(api, user, name="RFP-T_demo.pdf")
    assert response.status_code == 202
    body = response.json()
    assert (body["rfp_name"], body["requirement_count"]) == ("RFP-T", 2)

    run_id = body["id"]
    listing = api.get("/rfp/runs", headers=auth(user)).json()
    assert [r["id"] for r in listing] == [run_id]

    detail = api.get(f"/rfp/runs/{run_id}", headers=auth(user)).json()
    assert detail["state"] == "completed"
    assert detail["answered"] == 2
    assert detail["summary"]["pending"] == 2
    assert detail["summary"]["ready_to_export"] is False

    answers = api.get(f"/rfp/runs/{run_id}/results", headers=auth(user)).json()
    assert [a["requirement_id"] for a in answers] == ["T-001", "T-002"]
    assert answers[0]["ai_status"] == "compliant"
    assert answers[0]["citations"][0]["quote"].startswith("uses AES-256")


def test_a_second_run_is_refused_while_one_is_in_progress(db_session, api):
    user = make_user(db_session)
    db_session.add(RfpRun(created_by=user.id, rfp_name="X", source_filename="x.pdf"))
    db_session.flush()
    assert upload(api, user).status_code == 409


def test_other_people_get_404_everywhere(db_session, api):
    owner, other = make_user(db_session), make_user(db_session, name="other")
    run_id = upload(api, owner).json()["id"]
    headers = auth(other)
    assert api.get(f"/rfp/runs/{run_id}", headers=headers).status_code == 404
    assert api.get(f"/rfp/runs/{run_id}/results", headers=headers).status_code == 404
    assert api.get(f"/rfp/runs/{run_id}/export", headers=headers).status_code == 404
    review = {"action": "approve"}
    url = f"/rfp/runs/{run_id}/results/T-001/review"
    assert api.post(url, json=review, headers=headers).status_code == 404
    assert api.get("/rfp/runs", headers=headers).json() == []


def test_review_rules_are_enforced_through_the_api(db_session, api):
    user = make_user(db_session)
    run_id = upload(api, user).json()["id"]
    url = f"/rfp/runs/{run_id}/results/T-001/review"
    assert (
        api.post(
            url, json={"action": "edit", "final_status": "partial"}, headers=auth(user)
        ).status_code
        == 422
    )
    assert api.post(url, json={"action": "bless"}, headers=auth(user)).status_code == 422
    assert (
        api.post(url, json={"action": "approve", "sneaky": 1}, headers=auth(user)).status_code
        == 422
    )
    ok = api.post(url, json={"action": "approve"}, headers=auth(user))
    assert ok.status_code == 200
    assert (ok.json()["review_state"], ok.json()["final_status"]) == ("approved", "compliant")


def test_export_is_blocked_until_everything_is_reviewed(db_session, api):
    user = make_user(db_session)
    run_id = upload(api, user).json()["id"]
    export = f"/rfp/runs/{run_id}/export"
    assert api.get(export, headers=auth(user)).status_code == 409

    base = f"/rfp/runs/{run_id}/results"
    api.post(f"{base}/T-001/review", json={"action": "approve"}, headers=auth(user))
    assert api.get(export, headers=auth(user)).status_code == 409
    edited = {"action": "edit", "final_status": "partial", "note": NOTE}
    api.post(f"{base}/T-002/review", json=edited, headers=auth(user))

    response = api.get(export, headers=auth(user))
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    table = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [row[0] for row in table[1:]] == ["T-001", "T-002"]
    assert NOTE not in response.text
