import dataclasses
import random
import uuid
from datetime import date, timedelta

import pytest

from app.auth.policy import decide
from app.auth.policy_types import AclEntry, Decision, Reason, Resource, Subject
from app.models.enums import AclEffect, Classification, DocStatus, Purpose, Role, SubjectType
from tests.factories import make_resource, make_subject

TODAY = date(2026, 11, 8)
YESTERDAY = TODAY - timedelta(days=1)
TOMORROW = TODAY + timedelta(days=1)

ME = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)

PUBLIC = Classification.PUBLIC
INTERNAL = Classification.INTERNAL
CONFIDENTIAL = Classification.CONFIDENTIAL
RESTRICTED = Classification.RESTRICTED

ALLOW = AclEffect.ALLOW
DENY = AclEffect.DENY

ALL_ROLES = frozenset(r.value for r in Role)
BOTH = frozenset({"rfp", "enterprise_qa"})


def subj(**overrides):
    """An active employee whose id is ME, so ACL entries can name them."""
    overrides.setdefault("id", ME)
    return make_subject(**overrides)


def user_rule(effect, who=ME):
    return AclEntry(SubjectType.USER, str(who), effect)


def role_rule(effect, role):
    return AclEntry(SubjectType.ROLE, role, effect)


# ---------------------------------------------------------------------------
# Part 1: the rule table. Defaults: active employee in sales, internal clearance,
# asking to use an active internal document for the "rfp" purpose.
# ---------------------------------------------------------------------------


def case(case_id, subject, resource, purpose, allowed, reason):
    return pytest.param(subject, resource, purpose, allowed, reason, id=case_id)


RULE_CASES = [
    # Rule 1: disabled accounts
    case("1-inactive-user", {"is_active": False}, {}, "rfp", False, Reason.USER_INACTIVE),
    # Rule 2: only active documents
    case("2-draft", {}, {"status": DocStatus.DRAFT}, "rfp", False, Reason.DOCUMENT_NOT_ACTIVE),
    case(
        "2-superseded",
        {},
        {"status": DocStatus.SUPERSEDED},
        "rfp",
        False,
        Reason.DOCUMENT_NOT_ACTIVE,
    ),
    case(
        "2-archived", {}, {"status": DocStatus.ARCHIVED}, "rfp", False, Reason.DOCUMENT_NOT_ACTIVE
    ),
    case(
        "2-parse-failed",
        {},
        {"status": DocStatus.PARSE_FAILED},
        "rfp",
        False,
        Reason.DOCUMENT_NOT_ACTIVE,
    ),
    # Rule 3: expiry blocks RFP use only
    case(
        "3-expired-for-rfp", {}, {"valid_until": YESTERDAY}, "rfp", False, Reason.DOCUMENT_EXPIRED
    ),
    case(
        "3-expires-today-is-still-valid",
        {},
        {"valid_until": TODAY},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "3-expires-tomorrow-is-valid",
        {},
        {"valid_until": TOMORROW},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "3-expired-is-fine-for-qa",
        {},
        {"valid_until": YESTERDAY, "allowed_purposes": BOTH},
        "enterprise_qa",
        True,
        Reason.GENERAL_ACCESS,
    ),
    # Rule 4: purpose limitation
    case(
        "4-purpose-not-listed",
        {},
        {"allowed_purposes": frozenset({"enterprise_qa"})},
        "rfp",
        False,
        Reason.PURPOSE_NOT_ALLOWED,
    ),
    case(
        "4-no-purposes-listed",
        {},
        {"allowed_purposes": frozenset()},
        "rfp",
        False,
        Reason.PURPOSE_NOT_ALLOWED,
    ),
    case(
        "4-unknown-purpose",
        {},
        {"allowed_purposes": frozenset({"marketing"})},
        "marketing",
        False,
        Reason.PURPOSE_NOT_ALLOWED,
    ),
    case(
        "4-purpose-checked-before-acl",
        {},
        {"allowed_purposes": frozenset(), "acl": (user_rule(DENY),)},
        "rfp",
        False,
        Reason.PURPOSE_NOT_ALLOWED,
    ),
    # Rule 5: explicit deny always wins
    case("5-deny-for-user", {}, {"acl": (user_rule(DENY),)}, "rfp", False, Reason.EXPLICIT_DENY),
    case(
        "5-deny-for-role",
        {},
        {"acl": (role_rule(DENY, "employee"),)},
        "rfp",
        False,
        Reason.EXPLICIT_DENY,
    ),
    case(
        "5-deny-for-other-user-ignored",
        {},
        {"acl": (user_rule(DENY, OTHER),)},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "5-deny-for-other-role-ignored",
        {},
        {"acl": (role_rule(DENY, "auditor"),)},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "5-deny-beats-allow",
        {},
        {"acl": (role_rule(ALLOW, "employee"), user_rule(DENY))},
        "rfp",
        False,
        Reason.EXPLICIT_DENY,
    ),
    case(
        "5-deny-beats-allow-reversed",
        {},
        {"acl": (user_rule(DENY), role_rule(ALLOW, "employee"))},
        "rfp",
        False,
        Reason.EXPLICIT_DENY,
    ),
    # Rule 6: explicit allow (beats clearance, department and role, nothing earlier)
    case(
        "6-allow-for-user-on-restricted",
        {},
        {"classification": RESTRICTED, "acl": (user_rule(ALLOW),)},
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    case(
        "6-allow-for-role",
        {},
        {"classification": RESTRICTED, "acl": (role_rule(ALLOW, "employee"),)},
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    case(
        "6-allow-overrides-clearance",
        {"clearance": PUBLIC, "department": None},
        {
            "classification": CONFIDENTIAL,
            "allowed_roles": frozenset(),
            "acl": (user_rule(ALLOW),),
        },
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    case(
        "6-allow-overrides-department",
        {"clearance": CONFIDENTIAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": "finance", "acl": (user_rule(ALLOW),)},
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    case(
        "6-allow-cannot-revive-inactive-user",
        {"is_active": False},
        {"acl": (user_rule(ALLOW),)},
        "rfp",
        False,
        Reason.USER_INACTIVE,
    ),
    case(
        "6-allow-cannot-revive-draft",
        {},
        {"status": DocStatus.DRAFT, "acl": (user_rule(ALLOW),)},
        "rfp",
        False,
        Reason.DOCUMENT_NOT_ACTIVE,
    ),
    case(
        "6-allow-cannot-bypass-purpose",
        {},
        {"allowed_purposes": frozenset(), "acl": (user_rule(ALLOW),)},
        "rfp",
        False,
        Reason.PURPOSE_NOT_ALLOWED,
    ),
    case(
        "6-allow-cannot-revive-expired",
        {},
        {"valid_until": YESTERDAY, "acl": (user_rule(ALLOW),)},
        "rfp",
        False,
        Reason.DOCUMENT_EXPIRED,
    ),
    # Rule 7: administrators get no content through the general path
    case(
        "7-admin-denied-on-general-path",
        {"role": Role.ADMIN},
        {"classification": PUBLIC, "allowed_roles": ALL_ROLES},
        "rfp",
        False,
        Reason.ADMIN_NO_CONTENT_ACCESS,
    ),
    case(
        "7-admin-with-explicit-user-allow",
        {"role": Role.ADMIN},
        {"acl": (user_rule(ALLOW),)},
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    case(
        "7-admin-with-explicit-role-allow",
        {"role": Role.ADMIN},
        {"acl": (role_rule(ALLOW, "admin"),)},
        "rfp",
        True,
        Reason.EXPLICIT_ALLOW,
    ),
    # Rule 8: restricted documents need an explicit allow
    case(
        "8-restricted-needs-grant",
        {"role": Role.EXECUTIVE, "department": "executive", "clearance": RESTRICTED},
        {"classification": RESTRICTED, "allowed_roles": frozenset({"executive"})},
        "rfp",
        False,
        Reason.RESTRICTED_NEEDS_GRANT,
    ),
    # Rule 9: the role must be listed
    case(
        "9-role-not-listed",
        {},
        {"allowed_roles": frozenset({"executive"})},
        "rfp",
        False,
        Reason.ROLE_NOT_ALLOWED,
    ),
    case(
        "9-no-roles-listed",
        {},
        {"allowed_roles": frozenset()},
        "rfp",
        False,
        Reason.ROLE_NOT_ALLOWED,
    ),
    # Rule 10: clearance
    case(
        "10-clearance-too-low",
        {"clearance": PUBLIC},
        {"classification": INTERNAL},
        "rfp",
        False,
        Reason.CLEARANCE_TOO_LOW,
    ),
    case(
        "10-equal-clearance-ok",
        {"clearance": INTERNAL},
        {"classification": INTERNAL},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "10-higher-clearance-ok",
        {"clearance": CONFIDENTIAL},
        {"classification": INTERNAL},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "10-clearance-checked-before-department",
        {"clearance": INTERNAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": "sales"},
        "rfp",
        False,
        Reason.CLEARANCE_TOO_LOW,
    ),
    # Rule 11: confidential documents need the same department
    case(
        "11-department-mismatch",
        {"clearance": CONFIDENTIAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": "security"},
        "rfp",
        False,
        Reason.DEPARTMENT_MISMATCH,
    ),
    case(
        "11-document-without-department",
        {"clearance": CONFIDENTIAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": None},
        "rfp",
        False,
        Reason.DEPARTMENT_MISMATCH,
    ),
    case(
        "11-user-without-department",
        {"clearance": CONFIDENTIAL, "department": None},
        {"classification": CONFIDENTIAL, "department": "sales"},
        "rfp",
        False,
        Reason.DEPARTMENT_MISMATCH,
    ),
    case(
        "11-neither-has-department",
        {"clearance": CONFIDENTIAL, "department": None},
        {"classification": CONFIDENTIAL, "department": None},
        "rfp",
        False,
        Reason.DEPARTMENT_MISMATCH,
    ),
    case(
        "11-same-department-ok",
        {"clearance": CONFIDENTIAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": "sales"},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    case(
        "11-department-match-is-exact",
        {"clearance": CONFIDENTIAL, "department": "sales"},
        {"classification": CONFIDENTIAL, "department": "Sales"},
        "rfp",
        False,
        Reason.DEPARTMENT_MISMATCH,
    ),
    case(
        "11-internal-ignores-department",
        {"clearance": INTERNAL, "department": "sales"},
        {"classification": INTERNAL, "department": "security"},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
    # Rule 12: everything passed
    case(
        "12-external-reads-public",
        {"role": Role.EXTERNAL, "department": None, "clearance": PUBLIC},
        {"classification": PUBLIC, "allowed_roles": ALL_ROLES},
        "rfp",
        True,
        Reason.GENERAL_ACCESS,
    ),
]


@pytest.mark.parametrize(("subject", "resource", "purpose", "allowed", "reason"), RULE_CASES)
def test_rule_table(subject, resource, purpose, allowed, reason):
    decision = decide(subj(**subject), make_resource(**resource), purpose, TODAY)
    assert decision == Decision(allowed, reason)


def test_every_reason_is_exercised_by_the_rule_table():
    covered = {param.values[4] for param in RULE_CASES}
    assert covered == set(Reason)


# ---------------------------------------------------------------------------
# Part 2: the ten demo users against realistic documents.
# ---------------------------------------------------------------------------


def person(number, role, department, clearance, is_active=True):
    return Subject(uuid.UUID(int=number), role, department, clearance, is_active)


USERS = {
    "ceo": person(10, Role.EXECUTIVE, "executive", RESTRICTED),
    "cfo": person(11, Role.EXECUTIVE, "finance", RESTRICTED),
    "eng": person(12, Role.EMPLOYEE, "engineering", CONFIDENTIAL),
    "security": person(13, Role.EMPLOYEE, "security", CONFIDENTIAL),
    "sales": person(14, Role.EMPLOYEE, "sales", INTERNAL),
    "hr_head": person(15, Role.EMPLOYEE, "hr", CONFIDENTIAL),
    "auditor": person(16, Role.AUDITOR, "compliance", CONFIDENTIAL),
    "client": person(17, Role.EXTERNAL, None, PUBLIC),
    "admin": person(18, Role.ADMIN, "it", INTERNAL),
    "former": person(19, Role.EMPLOYEE, "sales", INTERNAL, is_active=False),
}

DOCS = {
    "security_architecture": Resource(
        classification=CONFIDENTIAL,
        department="engineering",
        allowed_roles=frozenset({"employee", "executive"}),
        allowed_purposes=frozenset({"rfp"}),
        status=DocStatus.ACTIVE,
        valid_until=None,
    ),
    "fy25_financials": Resource(
        classification=RESTRICTED,
        department="finance",
        allowed_roles=frozenset({"executive"}),
        allowed_purposes=frozenset({"enterprise_qa"}),
        status=DocStatus.ACTIVE,
        valid_until=None,
        acl=(user_rule(ALLOW, USERS["cfo"].id),),
    ),
    "handbook": Resource(
        classification=INTERNAL,
        department="hr",
        allowed_roles=frozenset({"employee"}),
        allowed_purposes=frozenset({"enterprise_qa"}),
        status=DocStatus.ACTIVE,
        valid_until=None,
    ),
    "salary_bands": Resource(
        classification=RESTRICTED,
        department="hr",
        allowed_roles=frozenset({"employee"}),
        allowed_purposes=frozenset(),
        status=DocStatus.ACTIVE,
        valid_until=None,
        acl=(user_rule(ALLOW, USERS["hr_head"].id),),
    ),
    "public_cert": Resource(
        classification=PUBLIC,
        department=None,
        allowed_roles=ALL_ROLES,
        allowed_purposes=BOTH,
        status=DocStatus.ACTIVE,
        valid_until=None,
    ),
    "iso9001_expired": Resource(
        classification=PUBLIC,
        department=None,
        allowed_roles=ALL_ROLES,
        allowed_purposes=BOTH,
        status=DocStatus.ACTIVE,
        valid_until=date(2024, 12, 31),
    ),
    "conflicted": Resource(
        classification=INTERNAL,
        department=None,
        allowed_roles=frozenset({"employee"}),
        allowed_purposes=frozenset({"rfp"}),
        status=DocStatus.ACTIVE,
        valid_until=None,
        acl=(role_rule(DENY, "employee"), user_rule(ALLOW, USERS["eng"].id)),
    ),
}


def scenario(user, doc, purpose, allowed, reason):
    return pytest.param(user, doc, purpose, allowed, reason, id=f"{user}-{doc}-{purpose}")


SCENARIOS = [
    scenario("eng", "security_architecture", "rfp", True, Reason.GENERAL_ACCESS),
    scenario("sales", "security_architecture", "rfp", False, Reason.CLEARANCE_TOO_LOW),
    scenario("security", "security_architecture", "rfp", False, Reason.DEPARTMENT_MISMATCH),
    scenario("ceo", "security_architecture", "rfp", False, Reason.DEPARTMENT_MISMATCH),
    scenario("auditor", "security_architecture", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    scenario("client", "security_architecture", "rfp", False, Reason.ROLE_NOT_ALLOWED),
    scenario("cfo", "fy25_financials", "enterprise_qa", True, Reason.EXPLICIT_ALLOW),
    scenario("ceo", "fy25_financials", "enterprise_qa", False, Reason.RESTRICTED_NEEDS_GRANT),
    scenario("cfo", "fy25_financials", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    scenario("eng", "handbook", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    scenario("eng", "handbook", "enterprise_qa", True, Reason.GENERAL_ACCESS),
    scenario("client", "handbook", "enterprise_qa", False, Reason.ROLE_NOT_ALLOWED),
    scenario("hr_head", "salary_bands", "enterprise_qa", False, Reason.PURPOSE_NOT_ALLOWED),
    scenario("hr_head", "salary_bands", "rfp", False, Reason.PURPOSE_NOT_ALLOWED),
    scenario("admin", "handbook", "enterprise_qa", False, Reason.ADMIN_NO_CONTENT_ACCESS),
    scenario("admin", "public_cert", "rfp", False, Reason.ADMIN_NO_CONTENT_ACCESS),
    scenario("former", "public_cert", "rfp", False, Reason.USER_INACTIVE),
    scenario("client", "public_cert", "rfp", True, Reason.GENERAL_ACCESS),
    scenario("auditor", "public_cert", "rfp", True, Reason.GENERAL_ACCESS),
    scenario("eng", "iso9001_expired", "rfp", False, Reason.DOCUMENT_EXPIRED),
    scenario("eng", "iso9001_expired", "enterprise_qa", True, Reason.GENERAL_ACCESS),
    scenario("eng", "conflicted", "rfp", False, Reason.EXPLICIT_DENY),
    scenario("sales", "conflicted", "rfp", False, Reason.EXPLICIT_DENY),
]


@pytest.mark.parametrize(("user", "doc", "purpose", "allowed", "reason"), SCENARIOS)
def test_demo_user_scenarios(user, doc, purpose, allowed, reason):
    assert decide(USERS[user], DOCS[doc], purpose, TODAY) == Decision(allowed, reason)


# ---------------------------------------------------------------------------
# Part 3: safety properties over 30,000 random but reproducible situations.
# ---------------------------------------------------------------------------

ROLE_LIST = list(Role)
CLEARANCES = list(Classification)
STATUSES = list(DocStatus)
PURPOSES = ["rfp", "enterprise_qa", "marketing"]
DEPARTMENTS = [None, "sales", "security"]
ROLE_SETS = [frozenset(), frozenset({"employee"}), frozenset({"executive", "auditor"}), ALL_ROLES]
PURPOSE_SETS = [
    frozenset(),
    frozenset({"rfp"}),
    frozenset({"enterprise_qa"}),
    BOTH,
    frozenset({"marketing", "rfp"}),
]
VALID_UNTIL = [None, YESTERDAY, TODAY, TOMORROW]


def random_acl(rng):
    entries = []
    for _ in range(rng.choice([0, 0, 1, 2, 3])):
        if rng.random() < 0.5:
            kind, who = SubjectType.USER, str(rng.choice([ME, OTHER]))
        else:
            kind, who = SubjectType.ROLE, rng.choice(ROLE_LIST).value
        entries.append(AclEntry(kind, who, rng.choice([ALLOW, DENY])))
    return tuple(entries)


def random_case(rng):
    subject = Subject(
        ME,
        rng.choice(ROLE_LIST),
        rng.choice(DEPARTMENTS),
        rng.choice(CLEARANCES),
        rng.random() < 0.9,
    )
    resource = Resource(
        classification=rng.choice(CLEARANCES),
        department=rng.choice(DEPARTMENTS),
        allowed_roles=rng.choice(ROLE_SETS),
        allowed_purposes=rng.choice(PURPOSE_SETS),
        status=rng.choice(STATUSES),
        valid_until=rng.choice(VALID_UNTIL),
        acl=random_acl(rng),
    )
    return subject, resource, rng.choice(PURPOSES)


_rng = random.Random(20261108)
CASES = [random_case(_rng) for _ in range(30000)]


def applicable_rules(subject, resource):
    return [
        e
        for e in resource.acl
        if (e.subject_type == SubjectType.USER and e.subject_id == str(subject.id))
        or (e.subject_type == SubjectType.ROLE and e.subject_id == subject.role.value)
    ]


def test_random_sample_reaches_every_reason():
    seen = {decide(s, r, p, TODAY).reason for s, r, p in CASES}
    assert seen == set(Reason)


def test_an_allowed_decision_always_meets_the_hard_requirements():
    for subject, resource, purpose in CASES:
        decision = decide(subject, resource, purpose, TODAY)
        if not decision.allowed:
            continue
        context = (subject, resource, purpose, decision)

        assert subject.is_active, context
        assert resource.status == DocStatus.ACTIVE, context
        assert purpose in {"rfp", "enterprise_qa"}, context
        assert purpose in resource.allowed_purposes, context
        if purpose == "rfp" and resource.valid_until is not None:
            assert resource.valid_until >= TODAY, context

        rules = applicable_rules(subject, resource)
        assert not any(e.effect == DENY for e in rules), context

        if decision.reason == Reason.EXPLICIT_ALLOW:
            assert any(e.effect == ALLOW for e in rules), context
        else:
            assert decision.reason == Reason.GENERAL_ACCESS, context
            assert subject.role != Role.ADMIN, context
            assert resource.classification != RESTRICTED, context
            assert subject.role.value in resource.allowed_roles, context
            assert subject.clearance.level >= resource.classification.level, context
            if resource.classification == CONFIDENTIAL:
                assert subject.department is not None, context
                assert subject.department == resource.department, context


def test_the_reason_always_matches_the_outcome():
    allow_reasons = {Reason.EXPLICIT_ALLOW, Reason.GENERAL_ACCESS}
    for subject, resource, purpose in CASES:
        decision = decide(subject, resource, purpose, TODAY)
        assert decision.allowed == (decision.reason in allow_reasons), decision


def test_lowering_clearance_never_grants_more():
    for subject, resource, purpose in CASES[:5000]:
        original = decide(subject, resource, purpose, TODAY)
        for lower in Classification:
            if lower.level >= subject.clearance.level:
                continue
            weaker = dataclasses.replace(subject, clearance=lower)
            if decide(weaker, resource, purpose, TODAY).allowed:
                assert original.allowed, (subject, resource, purpose, lower)


def test_deactivating_a_user_always_denies():
    for subject, resource, purpose in CASES[:5000]:
        off = dataclasses.replace(subject, is_active=False)
        assert decide(off, resource, purpose, TODAY) == Decision(False, Reason.USER_INACTIVE)


def test_adding_a_deny_rule_never_allows():
    for subject, resource, purpose in CASES[:5000]:
        denied = dataclasses.replace(resource, acl=resource.acl + (user_rule(DENY, subject.id),))
        assert not decide(subject, denied, purpose, TODAY).allowed, (subject, resource, purpose)


def test_the_order_of_acl_entries_does_not_matter():
    checked = 0
    for subject, resource, purpose in CASES:
        if len(resource.acl) < 2:
            continue
        flipped = dataclasses.replace(resource, acl=tuple(reversed(resource.acl)))
        before = decide(subject, resource, purpose, TODAY)
        after = decide(subject, flipped, purpose, TODAY)
        assert before == after, (subject, resource, purpose)
        checked += 1
    assert checked > 1000


def test_a_document_with_no_roles_and_no_purposes_is_closed_to_everyone():
    closed = make_resource(allowed_roles=frozenset(), allowed_purposes=frozenset())
    for role in Role:
        for clearance in Classification:
            for purpose in Purpose:
                subject = subj(role=role, clearance=clearance)
                assert not decide(subject, closed, purpose, TODAY).allowed


def test_purpose_can_be_given_as_enum_or_string():
    resource = make_resource(allowed_purposes=BOTH)
    for purpose in Purpose:
        as_enum = decide(subj(), resource, purpose, TODAY)
        as_text = decide(subj(), resource, purpose.value, TODAY)
        assert as_enum == as_text
