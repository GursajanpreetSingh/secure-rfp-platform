import pytest

from app.auth.passwords import (
    DUMMY_HASH,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    hash_password,
    verify_password,
)

GOOD = "correct horse battery"


def test_hash_is_argon2id_and_hides_password():
    h = hash_password(GOOD)
    assert h.startswith("$argon2id$")
    assert GOOD not in h


def test_correct_password_verifies():
    assert verify_password(GOOD, hash_password(GOOD)) is True


def test_wrong_password_is_rejected():
    assert verify_password("some other password", hash_password(GOOD)) is False


def test_same_password_gets_different_hashes():
    assert hash_password(GOOD) != hash_password(GOOD)


def test_too_short_password_is_rejected():
    with pytest.raises(ValueError):
        hash_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_too_long_password_is_rejected():
    with pytest.raises(ValueError):
        hash_password("x" * (MAX_PASSWORD_LENGTH + 1))


def test_overlong_password_never_verifies():
    assert verify_password("x" * (MAX_PASSWORD_LENGTH + 1), hash_password(GOOD)) is False


@pytest.mark.parametrize("bad_hash", ["", "not-a-hash", "$argon2id$broken"])
def test_malformed_hash_returns_false(bad_hash):
    assert verify_password(GOOD, bad_hash) is False


def test_dummy_hash_is_a_valid_argon2_hash():
    assert DUMMY_HASH.startswith("$argon2id$")
    assert verify_password("not-a-real-password", DUMMY_HASH) is True
