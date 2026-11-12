import dataclasses
import re

import pytest

from app.auth.policy_types import AclEntry, Decision, Reason
from app.models.enums import AclEffect, SubjectType
from tests.factories import make_resource, make_subject


def test_reason_codes_match_the_rule_table():
    values = [r.value for r in Reason]
    assert len(values) == 12
    assert len(set(values)) == 12
    assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", v) for v in values)


def test_subject_is_immutable():
    subject = make_subject()
    with pytest.raises(dataclasses.FrozenInstanceError):
        subject.is_active = False


def test_resource_is_immutable():
    resource = make_resource()
    with pytest.raises(dataclasses.FrozenInstanceError):
        resource.allowed_roles = frozenset({"admin"})


def test_resource_has_no_acl_entries_by_default():
    assert make_resource().acl == ()


def test_acl_entries_are_stored_as_given():
    entry = AclEntry(SubjectType.ROLE, "employee", AclEffect.DENY)
    resource = make_resource(acl=(entry,))
    assert resource.acl == (entry,)


def test_decision_holds_outcome_and_reason():
    decision = Decision(allowed=False, reason=Reason.CLEARANCE_TOO_LOW)
    assert decision.allowed is False
    assert decision.reason == "clearance_too_low"
