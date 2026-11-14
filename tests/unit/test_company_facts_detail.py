from pathlib import Path

import pytest
import yaml

FACTS_PATH = Path(__file__).resolve().parents[2] / "data" / "company_facts.yaml"

DETAIL_SECTIONS = [
    "certification_details",
    "performance_test",
    "architecture",
    "incident_response",
    "support_details",
    "reference_details",
    "old_documents",
    "policy_register",
    "fy25_detail",
    "hr_policy",
    "salary_bands",
]


@pytest.fixture(scope="module")
def facts():
    with FACTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_without(facts, *excluded):
    """All sections except the excluded ones, written back out as lowercase text."""
    kept = {k: v for k, v in facts.items() if k not in excluded}
    return yaml.safe_dump(kept).lower()


def test_detail_sections_are_present(facts):
    missing = [s for s in DETAIL_SECTIONS if s not in facts]
    assert not missing, f"missing sections: {missing}"


def test_certification_details_refer_to_real_certificates(facts):
    known = {c["id"] for c in facts["certifications"]}
    details = facts["certification_details"]
    assert set(details) == {"CERT-ISO27001", "CERT-ISO9001"}
    assert set(details) <= known


def test_certification_audit_dates_make_sense(facts):
    today = facts["as_of_date"]
    certs = {c["id"]: c for c in facts["certifications"]}
    for cert_id, detail in facts["certification_details"].items():
        cert = certs[cert_id]
        assert detail["stage1_audit"] < detail["stage2_audit"] <= cert["issued"], cert_id
        for audit in detail["surveillance_audits"]:
            assert cert["issued"] < audit < cert["expires"], cert_id
            assert audit <= today, cert_id
    iso = facts["certification_details"]["CERT-ISO27001"]
    assert today < iso["recertification_audit_planned"] < certs["CERT-ISO27001"]["expires"]


def test_all_audit_findings_are_closed(facts):
    for cert_id, detail in facts["certification_details"].items():
        findings = detail["findings"]
        assert findings["major"] == 0, cert_id
        assert findings["minor_closed"] == findings["minor_raised"], cert_id


def test_annex_a_numbers_add_up(facts):
    annex = facts["certification_details"]["CERT-ISO27001"]["annex_a"]
    assert sum(annex["themes"].values()) == annex["total_controls"] == 93
    assert annex["applicable_controls"] == annex["total_controls"] - len(annex["exclusions"])
    controls = [e["control"] for e in annex["exclusions"]]
    assert len(controls) == len(set(controls))


def test_performance_stages_are_consistent(facts):
    perf = facts["performance"]
    test = facts["performance_test"]
    stages = test["stages"]
    users = [s["users"] for s in stages]

    assert users == sorted(set(users))
    assert max(users) == test["highest_load_tested"] == perf["tested_concurrent_users"]
    assert test["highest_load_tested"] < 10000
    assert stages[-1]["p95_ms"] == perf["p95_latency_ms"]

    criteria = test["acceptance_criteria"]
    for stage in stages:
        assert stage["p50_ms"] < stage["p95_ms"] < stage["p99_ms"], stage
        assert stage["p95_ms"] <= criteria["p95_ms_max"], stage
        assert stage["error_percent"] <= criteria["error_percent_max"], stage

    for key in ("p95_ms", "requests_per_second", "app_cpu_percent", "error_percent"):
        values = [s[key] for s in stages]
        assert values == sorted(values), key


def test_architecture_matches_the_security_facts(facts):
    arch = facts["architecture"]
    security = facts["security"]
    assert arch["encryption"]["at_rest"] == security["encryption_at_rest"]
    assert arch["encryption"]["in_transit"] == security["encryption_in_transit"]
    assert arch["encryption"]["key_rotation_days"] == security["key_rotation_days"]
    regions = " ".join(arch["regions"])
    for residency in security["data_residency"]:
        assert residency in regions


def test_architecture_components_are_well_formed(facts):
    arch = facts["architecture"]
    names = [c["name"] for c in arch["components"]]
    assert len(names) == len(set(names))
    assert len(names) >= 15
    assert {c["layer"] for c in arch["components"]} == set(arch["zones"])


def test_incident_response_matches_continuity(facts):
    response = facts["incident_response"]
    continuity = facts["continuity"]
    assert response["dr_test"]["date"] == continuity["last_dr_test_date"]
    assert response["dr_test"]["rto_achieved_hours"] <= continuity["rto_hours"]
    assert response["dr_test"]["rpo_achieved_hours"] <= continuity["rpo_hours"]
    levels = [s["level"] for s in response["severity_levels"]]
    assert levels == ["SEV1", "SEV2", "SEV3", "SEV4"]


def test_support_details_are_consistent(facts):
    support = facts["support"]
    tiers = facts["support_details"]["service_credits"]
    thresholds = [t["below_percent"] for t in tiers]
    credits = [t["credit_percent"] for t in tiers]
    assert support["support_24x7"] is False
    assert thresholds == sorted(thresholds, reverse=True)
    assert credits == sorted(credits)
    assert thresholds[0] == support["uptime_sla_percent"]


def test_reference_details_match_the_references(facts):
    ids = {r["id"] for r in facts["references"]}
    assert set(facts["reference_details"]) == ids
    for detail in facts["reference_details"].values():
        assert detail["duration_months"] > 0


def test_old_documents_still_conflict_with_current_facts(facts):
    security = facts["security"]
    brochure = facts["old_documents"]["brochure_2022"]["claims"]
    old_policy = facts["old_documents"]["security_policy_v1"]["claims"]
    assert brochure["encryption_at_rest"] != security["encryption_at_rest"]
    assert brochure["uptime_sla_percent"] != facts["support"]["uptime_sla_percent"]
    assert brochure["hosting_regions"] != security["data_residency"]
    assert old_policy["mfa_required"] != security["mfa_required"]
    assert old_policy["password_min_length"] != security["password_min_length"]
    assert old_policy["log_retention_days"] != security["log_retention_days"]


def test_superseded_dates_agree_everywhere(facts):
    old = facts["old_documents"]
    superseded = {s["id"]: s for s in facts["superseded_facts"]}
    brochure_date = old["brochure_2022"]["superseded_on"]
    policy_date = old["security_policy_v1"]["superseded_on"]
    register = facts["policy_register"]["information_security_policy"]

    assert brochure_date == superseded["OLD-BROCHURE-2022"]["superseded_on"]
    assert policy_date == superseded["OLD-POLICY-V1"]["superseded_on"]
    assert policy_date == register["current_effective"]
    assert register["current_effective"] <= facts["as_of_date"]


def test_the_draft_proposal_is_a_future_unapproved_promise(facts):
    draft = facts["old_documents"]["draft_support_proposal"]
    assert draft["status"] == "draft"
    assert draft["proposed_start"] > facts["as_of_date"]


def test_finance_detail_adds_up(facts):
    detail = facts["fy25_detail"]
    revenue = facts["restricted"]["fy25_revenue_inr_crore"]
    assert sum(detail["revenue_segments_inr_crore"].values()) == revenue
    growth = (revenue / detail["fy24_revenue_inr_crore"] - 1) * 100
    assert round(growth) == detail["revenue_growth_percent"]
    assert detail["customers"] > 0


def test_salary_bands_are_consistent(facts):
    bands = facts["salary_bands"]["bands"]
    keys = [(b["family"], b["level"]) for b in bands]
    assert len(keys) == len(set(keys))

    families = {}
    for band in bands:
        assert band["min"] < band["max"], band
        families.setdefault(band["family"], []).append(band)
    assert set(families) == {"engineering", "security", "sales", "support", "hr", "finance"}

    for family, rows in families.items():
        assert [r["min"] for r in rows] == sorted(r["min"] for r in rows), family
        assert [r["max"] for r in rows] == sorted(r["max"] for r in rows), family

    engineer = next(b for b in bands if b["family"] == "engineering" and b["title"] == "Engineer")
    assert f"{engineer['min']}-{engineer['max']}" == facts["restricted"]["salary_band_engineer_lpa"]


def test_claim_phrases_appear_only_where_intended(facts):
    outside_draft = dump_without(facts, "old_documents", "not_documented")
    assert "24/7" not in outside_draft

    outside_old = dump_without(facts, "old_documents", "superseded_facts", "not_documented")
    assert "aes-128" not in outside_old
