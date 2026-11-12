import re

import pytest

from app.audit.service import MAX_DETAIL_BYTES, check_detail, email_digest


def test_plain_detail_is_accepted():
    detail = {"reason": "clearance_too_low", "chunk_ids": ["a", "b"], "count": 2}
    assert check_detail(detail) == detail


@pytest.mark.parametrize(
    "detail",
    [
        {"password": "x"},
        {"Password": "x"},
        {"new_password": "x"},
        {"access_token": "x"},
        {"Authorization": "Bearer x"},
        {"client_secret": "x"},
        {"document_content": "some text"},
        {"snippet": "some text"},
        {"password_hash": "x"},
        {"outer": {"inner": {"token": "x"}}},
        {"items": [{"cookie": "x"}]},
    ],
)
def test_secret_looking_keys_are_rejected(detail):
    with pytest.raises(ValueError):
        check_detail(detail)


def test_values_that_are_not_plain_json_are_rejected():
    with pytest.raises(ValueError):
        check_detail({"ids": {1, 2, 3}})
    with pytest.raises(ValueError):
        check_detail({"thing": object()})


def test_oversized_detail_is_rejected():
    with pytest.raises(ValueError):
        check_detail({"note": "x" * (MAX_DETAIL_BYTES + 1)})


def test_email_digest_is_short_hex_and_repeatable():
    digest = email_digest("alice@example.test")
    assert re.fullmatch(r"[0-9a-f]{16}", digest)
    assert digest == email_digest("alice@example.test")


def test_email_digest_ignores_case_and_spaces():
    assert email_digest("  Alice@Example.TEST ") == email_digest("alice@example.test")


def test_email_digest_differs_between_emails():
    assert email_digest("alice@example.test") != email_digest("bob@example.test")


def test_email_digest_does_not_contain_the_email():
    assert "alice" not in email_digest("alice@example.test")
