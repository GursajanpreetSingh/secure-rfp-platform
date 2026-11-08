from datetime import date
from pathlib import Path

import pytest
import yaml

FACTS_PATH = Path(__file__).resolve().parents[2] / "data" / "company_facts.yaml"

REQUIRED_SECTIONS = [
    "as_of_date",
    "company",
    "certifications",
    "security",
    "continuity",
    "performance",
    "support",
    "privacy",
    "references",
    "subcontractors",
    "hr",
    "restricted",
    "superseded_facts",
    "not_documented",
]


@pytest.fixture(scope="module")
def facts():
    with FACTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(facts, dotted_path):
    """Follow a path like 'security.mfa_required' through nested dictionaries."""
    node = facts
    for part in dotted_path.split("."):
        node = node[part]
    return node


def test_required_sections_present(facts):
    missing = [s for s in REQUIRED_SECTIONS if s not in facts]
    assert not missing, f"missing sections: {missing}"


def test_as_of_date_is_a_real_date(facts):
    assert isinstance(facts["as_of_date"], date)


def test_certificate_ids_and_document_keys_are_unique(facts):
    ids = [c["id"] for c in facts["certifications"]]
    keys = [c["document_key"] for c in facts["certifications"]]
    assert len(ids) == len(set(ids))
    assert len(keys) == len(set(keys))


def test_certificate_status_matches_its_dates(facts):
    today = facts["as_of_date"]
    for cert in facts["certifications"]:
        assert cert["issued"] <= today, f"{cert['id']} issued in the future"
        if cert["status"] == "active":
            assert cert["expires"] > today, f"{cert['id']} marked active but expired"
        elif cert["status"] == "expired":
            assert cert["expires"] < today, f"{cert['id']} marked expired but still valid"
        else:
            pytest.fail(f"{cert['id']} has unknown status {cert['status']!r}")


def test_deliberate_traps_are_in_place(facts):
    assert facts["support"]["support_24x7"] is False
    assert facts["performance"]["tested_concurrent_users"] < 10000
    assert facts["security"]["encryption_at_rest"] == "AES-256"
    assert facts["security"]["mfa_required"] == "all_staff"
    statuses = {c["id"]: c["status"] for c in facts["certifications"]}
    assert statuses["CERT-ISO9001"] == "expired"


def test_superseded_facts_point_to_real_current_facts(facts):
    for old in facts["superseded_facts"]:
        assert resolve(facts, old["replaced_by"]) is not None


def test_undocumented_items_appear_nowhere_else(facts):
    others = {k: v for k, v in facts.items() if k not in ("not_documented", "superseded_facts")}
    haystack = yaml.safe_dump(others).lower()
    for item in facts["not_documented"]:
        assert item.lower() not in haystack, f"{item} must not be documented anywhere"


def test_references_are_valid(facts):
    ids = [r["id"] for r in facts["references"]]
    assert len(ids) == len(set(ids))
    assert all(r["users"] > 0 for r in facts["references"])
