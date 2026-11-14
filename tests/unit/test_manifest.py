import uuid
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
import yaml

from app.auth.policy import decide
from app.auth.policy_types import Decision, Reason, Subject
from app.datagen.manifest import load_manifest, to_resource
from app.models.enums import AclEffect, Classification, DocStatus, Purpose, Role, SubjectType

ROOT = Path(__file__).resolve().parents[2]
FACTS_PATH = ROOT / "data" / "company_facts.yaml"
SEED_PATH = ROOT / "data" / "seed_users.yaml"

NAMES = {
    "ceo": "ceo@meridian.test",
    "cfo": "cfo@meridian.test",
    "eng": "eng@meridian.test",
    "security": "security@meridian.test",
    "sales": "sales@meridian.test",
    "hr.head": "hr.head@meridian.test",
    "auditor": "auditor@meridian.test",
    "client": "client@client.example",
    "admin": "admin@meridian.test",
    "former": "former@meridian.test",
}


def user_id(email):
    return uuid.uuid5(uuid.NAMESPACE_DNS, email)


@pytest.fixture(scope="module")
def manifest():
    return load_manifest()


@pytest.fixture(scope="module")
def docs(manifest):
    return {d.id: d for d in manifest.documents}


@pytest.fixture(scope="module")
def facts():
    with FACTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def today(facts):
    return facts["as_of_date"]


@pytest.fixture(scope="module")
def seed_users():
    with SEED_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["users"]


@pytest.fixture(scope="module")
def people(seed_users):
    return {
        u["email"]: Subject(
            user_id(u["email"]),
            Role(u["role"]),
            u["department"],
            Classification(u["clearance"]),
            u.get("is_active", True),
        )
        for u in seed_users
    }


@pytest.fixture(scope="module")
def resources(manifest, seed_users):
    ids = {u["email"]: user_id(u["email"]) for u in seed_users}
    return {d.id: to_resource(d, ids) for d in manifest.documents}


def resolve(facts, path):
    node = facts
    for part in path.split("."):
        node = node[part]
    return node


# ---------------------------------------------------------------------------
# Structure and consistency
# ---------------------------------------------------------------------------


def test_there_are_fourteen_documents_with_sequential_ids(manifest):
    ids = [d.id for d in manifest.documents]
    assert ids == [f"DOC-{n:03d}" for n in range(1, 15)]


def test_filenames_are_unique_and_match_id_and_format(manifest):
    names = [d.filename for d in manifest.documents]
    assert len(names) == len(set(names))
    for d in manifest.documents:
        assert d.filename.startswith(d.id + "_"), d.id
        assert d.filename.endswith("." + d.format), d.id


def test_format_counts(manifest):
    counts = Counter(d.format for d in manifest.documents)
    assert counts == {"pdf": 10, "docx": 3, "txt": 1}


def test_every_document_meets_the_page_target(manifest):
    assert manifest.minimum_pages == 20
    for d in manifest.documents:
        assert d.target_pages >= manifest.minimum_pages, d.id
    assert sum(d.target_pages for d in manifest.documents) >= 300


def test_only_the_intended_documents_are_not_active_or_expired(manifest, docs, today):
    inactive = {d.id for d in manifest.documents if d.status != DocStatus.ACTIVE}
    expired = {
        d.id for d in manifest.documents if d.valid_until is not None and d.valid_until < today
    }
    assert inactive == {"DOC-008", "DOC-010", "DOC-011"}
    assert expired == {"DOC-009"}
    assert docs["DOC-008"].status == DocStatus.SUPERSEDED
    assert docs["DOC-010"].status == DocStatus.SUPERSEDED
    assert docs["DOC-011"].status == DocStatus.DRAFT


def test_versions_of_one_document_are_consistent(manifest):
    groups = {}
    for d in manifest.documents:
        groups.setdefault(d.logical_key, []).append(d)
    for key, versions in groups.items():
        numbers = [d.version for d in versions]
        assert len(numbers) == len(set(numbers)), key
        newest = max(versions, key=lambda d: d.version)
        for d in versions:
            if d is not newest:
                assert d.status == DocStatus.SUPERSEDED, (key, d.id)

    policy = groups["information_security_policy"]
    assert {d.version for d in policy} == {1, 2}
    assert max(policy, key=lambda d: d.version).status == DocStatus.ACTIVE


def test_dates_are_sensible(manifest, today):
    for d in manifest.documents:
        assert d.document_date <= today, d.id
        if d.effective_date is not None:
            assert d.document_date <= d.effective_date <= today, d.id
        if d.superseded_on is not None:
            assert d.document_date < d.superseded_on <= today, d.id
            assert d.status == DocStatus.SUPERSEDED, d.id
        if d.valid_until is not None:
            assert d.valid_until >= d.document_date, d.id


def test_policy_documents_match_the_facts(docs, facts):
    register = facts["policy_register"]["information_security_policy"]
    v1 = facts["old_documents"]["security_policy_v1"]
    assert docs["DOC-001"].version == register["current_version"]
    assert docs["DOC-001"].effective_date == register["current_effective"]
    assert docs["DOC-008"].version == v1["version"]
    assert docs["DOC-008"].effective_date == v1["effective"]
    assert docs["DOC-008"].superseded_on == v1["superseded_on"]
    assert docs["DOC-008"].superseded_on == docs["DOC-001"].effective_date


def test_certificate_packages_match_the_facts(docs, facts):
    certs = {c["id"]: c for c in facts["certifications"]}
    assert docs["DOC-002"].valid_until == certs["CERT-ISO27001"]["expires"]
    assert docs["DOC-002"].document_date == certs["CERT-ISO27001"]["issued"]
    assert docs["DOC-009"].valid_until == certs["CERT-ISO9001"]["expires"]
    assert docs["DOC-009"].document_date == certs["CERT-ISO9001"]["issued"]


def test_trap_documents_match_the_facts(docs, facts):
    old = facts["old_documents"]
    assert docs["DOC-010"].superseded_on == old["brochure_2022"]["superseded_on"]
    assert docs["DOC-010"].document_date == old["brochure_2022"]["published"]
    assert docs["DOC-011"].status == DocStatus.DRAFT
    assert old["draft_support_proposal"]["proposed_start"] > docs["DOC-011"].document_date


def test_reports_postdate_the_events_they_describe(docs, facts):
    assert docs["DOC-004"].document_date > facts["performance"]["test_date"]
    assert docs["DOC-006"].document_date >= facts["incident_response"]["dr_test"]["date"]


def test_fact_references_resolve(manifest, facts):
    for d in manifest.documents:
        assert d.facts, d.id
        for path in d.facts:
            assert resolve(facts, path) is not None, (d.id, path)


def test_acl_rules_exist_only_on_restricted_documents(manifest, seed_users):
    emails = {u["email"] for u in seed_users}
    with_rules = {d.id for d in manifest.documents if d.acl}
    restricted = {d.id for d in manifest.documents if d.classification == Classification.RESTRICTED}
    assert with_rules == restricted == {"DOC-013", "DOC-014"}
    for d in manifest.documents:
        for rule in d.acl:
            assert rule.effect == AclEffect.ALLOW, d.id
            if rule.subject_type == SubjectType.USER:
                assert rule.subject in emails, (d.id, rule.subject)


# ---------------------------------------------------------------------------
# The loader refuses bad manifests
# ---------------------------------------------------------------------------


def valid_entry(**overrides):
    entry = {
        "id": "DOC-001",
        "title": "Test",
        "logical_key": "test",
        "version": 1,
        "filename": "DOC-001_test.pdf",
        "format": "pdf",
        "target_pages": 20,
        "document_type": "policy",
        "department": "security",
        "classification": "internal",
        "allowed_roles": ["employee"],
        "allowed_purposes": ["rfp"],
        "status": "active",
        "document_date": date(2025, 1, 1),
        "facts": ["security.mfa_required"],
    }
    entry.update(overrides)
    return entry


def write_manifest(tmp_path, entries):
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump({"minimum_pages": 20, "documents": entries}), encoding="utf-8")
    return path


def test_a_valid_manifest_loads(tmp_path):
    manifest = load_manifest(write_manifest(tmp_path, [valid_entry()]))
    assert len(manifest.documents) == 1
    assert manifest.documents[0].classification == Classification.INTERNAL


@pytest.mark.parametrize(
    "make_entries",
    [
        lambda: [valid_entry(classification="top-secret")],
        lambda: [valid_entry(colour="red")],
        lambda: [{k: v for k, v in valid_entry().items() if k != "facts"}],
        lambda: [valid_entry(), valid_entry(filename="DOC-001_other.pdf")],
    ],
    ids=["bad-classification", "unknown-key", "missing-key", "duplicate-id"],
)
def test_loader_rejects_bad_manifests(tmp_path, make_entries):
    path = write_manifest(tmp_path, make_entries())
    with pytest.raises(ValueError):
        load_manifest(path)


# ---------------------------------------------------------------------------
# The real policy applied to the real documents
# ---------------------------------------------------------------------------

MATRIX = [
    ("eng", "DOC-003", "rfp", True, Reason.GENERAL_ACCESS),
    ("eng", "DOC-004", "rfp", True, Reason.GENERAL_ACCESS),
    ("sales", "DOC-003", "rfp", False, Reason.CLEARANCE_TOO_LOW),
    ("security", "DOC-003", "rfp", False, Reason.DEPARTMENT_MISMATCH),
    ("ceo", "DOC-003", "rfp", False, Reason.DEPARTMENT_MISMATCH),
    ("auditor", "DOC-003", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    ("client", "DOC-003", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    ("eng", "DOC-001", "rfp", True, Reason.GENERAL_ACCESS),
    ("auditor", "DOC-001", "rfp", True, Reason.GENERAL_ACCESS),
    ("client", "DOC-001", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    ("client", "DOC-002", "rfp", True, Reason.GENERAL_ACCESS),
    ("client", "DOC-005", "rfp", True, Reason.GENERAL_ACCESS),
    ("client", "DOC-007", "rfp", True, Reason.GENERAL_ACCESS),
    ("eng", "DOC-006", "rfp", True, Reason.GENERAL_ACCESS),
    ("client", "DOC-006", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    ("eng", "DOC-008", "rfp", False, Reason.DOCUMENT_NOT_ACTIVE),
    ("eng", "DOC-009", "rfp", False, Reason.DOCUMENT_EXPIRED),
    ("eng", "DOC-009", "enterprise_qa", True, Reason.GENERAL_ACCESS),
    ("eng", "DOC-010", "rfp", False, Reason.DOCUMENT_NOT_ACTIVE),
    ("eng", "DOC-011", "rfp", False, Reason.DOCUMENT_NOT_ACTIVE),
    ("eng", "DOC-012", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    ("eng", "DOC-012", "enterprise_qa", True, Reason.GENERAL_ACCESS),
    ("client", "DOC-012", "enterprise_qa", False, Reason.ROLE_NOT_ALLOWED),
    ("cfo", "DOC-013", "enterprise_qa", True, Reason.EXPLICIT_ALLOW),
    ("ceo", "DOC-013", "enterprise_qa", False, Reason.RESTRICTED_NEEDS_GRANT),
    ("cfo", "DOC-013", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    ("eng", "DOC-013", "enterprise_qa", False, Reason.RESTRICTED_NEEDS_GRANT),
    ("hr.head", "DOC-014", "enterprise_qa", False, Reason.PURPOSE_NOT_ALLOWED),
    ("hr.head", "DOC-014", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    ("admin", "DOC-001", "enterprise_qa", False, Reason.ADMIN_NO_CONTENT_ACCESS),
    ("admin", "DOC-002", "rfp", False, Reason.ADMIN_NO_CONTENT_ACCESS),
    ("former", "DOC-002", "rfp", False, Reason.USER_INACTIVE),
]


@pytest.mark.parametrize(("user", "doc", "purpose", "allowed", "reason"), MATRIX)
def test_policy_decisions_on_the_real_documents(
    people, resources, today, user, doc, purpose, allowed, reason
):
    subject = people[NAMES[user]]
    assert decide(subject, resources[doc], purpose, today) == Decision(allowed, reason)


def test_a_disabled_account_reaches_nothing(people, resources, today):
    former = people[NAMES["former"]]
    for resource in resources.values():
        for purpose in Purpose:
            assert not decide(former, resource, purpose, today).allowed


def test_administrators_reach_nothing_without_a_rule(people, resources, today):
    admin = people[NAMES["admin"]]
    for resource in resources.values():
        for purpose in Purpose:
            assert not decide(admin, resource, purpose, today).allowed


def test_external_users_reach_only_public_documents(people, resources, today):
    client = people[NAMES["client"]]
    for doc_id, resource in resources.items():
        for purpose in Purpose:
            if decide(client, resource, purpose, today).allowed:
                assert resource.classification == Classification.PUBLIC, doc_id


def test_the_salary_document_is_unreachable_for_everyone(people, resources, today):
    for email, subject in people.items():
        for purpose in Purpose:
            assert not decide(subject, resources["DOC-014"], purpose, today).allowed, email


def test_the_financial_document_reaches_only_the_cfo(people, resources, today):
    reached = {
        name
        for name, email in NAMES.items()
        if any(decide(people[email], resources["DOC-013"], p, today).allowed for p in Purpose)
    }
    assert reached == {"cfo"}


def test_exactly_the_intended_documents_are_unreachable(people, resources, today):
    unreachable = {
        doc_id
        for doc_id, resource in resources.items()
        if not any(
            decide(subject, resource, purpose, today).allowed
            for subject in people.values()
            for purpose in Purpose
        )
    }
    assert unreachable == {"DOC-008", "DOC-010", "DOC-011", "DOC-014"}
