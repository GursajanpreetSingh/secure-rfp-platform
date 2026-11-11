from pathlib import Path

import pytest
import yaml

from app.models.enums import Classification, Role

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_users.yaml"


@pytest.fixture(scope="module")
def users():
    with SEED_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["users"]


def test_every_user_has_valid_role_and_clearance(users):
    for u in users:
        Role(u["role"])
        Classification(u["clearance"])


def test_emails_are_unique_lowercase_and_on_reserved_domains(users):
    emails = [u["email"] for u in users]
    assert len(emails) == len(set(emails))
    for email in emails:
        assert email == email.lower()
        assert email.endswith((".test", ".example")), f"{email} is not on a reserved domain"


def test_every_role_has_at_least_one_user(users):
    assert {u["role"] for u in users} == {r.value for r in Role}


def test_external_user_is_public_and_has_no_department(users):
    externals = [u for u in users if u["role"] == "external"]
    assert externals
    for u in externals:
        assert u["clearance"] == "public"
        assert u["department"] is None


def test_admin_has_low_clearance(users):
    for u in users:
        if u["role"] == "admin":
            assert Classification(u["clearance"]).level <= Classification.INTERNAL.level


def test_there_is_an_inactive_user_for_negative_tests(users):
    assert any(u.get("is_active", True) is False for u in users)


def test_file_contains_no_secrets(users):
    text = SEED_PATH.read_text(encoding="utf-8").lower()
    code_lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    body = "\n".join(code_lines)
    assert "password" not in body
    assert "secret" not in body
