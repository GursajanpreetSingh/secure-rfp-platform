"""The most important search test: the SQL access condition and decide() must always agree."""

import itertools
import random
import uuid
from datetime import date

import pytest
from sqlalchemy import delete, text

from app.auth.policy import decide
from app.auth.policy_types import AclEntry, Resource, Subject
from app.auth.seed import load_seed_users
from app.models import Chunk, Document, DocumentACL
from app.models.enums import (
    AclEffect,
    Classification,
    DocStatus,
    Purpose,
    Role,
    SubjectType,
)
from app.retrieval.access_sql import ACCESS_SQL, access_params

pytestmark = pytest.mark.integration

DEPARTMENTS = [None, "engineering", "sales", "security", "hr", "finance", "compliance"]
VALID_UNTIL = [None, date(2026, 1, 1), date(2026, 11, 16), date(2027, 1, 1)]
TODAYS = [date(2026, 11, 8), date(2026, 11, 16), date(2024, 6, 1), date(2027, 1, 1)]
DOCUMENTS = 600


def _subjects() -> list[Subject]:
    subjects = [
        Subject(
            id=uuid.uuid5(uuid.NAMESPACE_DNS, user["email"]),
            role=Role(user["role"]),
            department=user.get("department"),
            clearance=Classification(user["clearance"]),
            is_active=user.get("is_active", True),
        )
        for user in load_seed_users()
    ]
    # Two edge cases the demo users do not cover.
    subjects.append(Subject(uuid.uuid4(), Role.EMPLOYEE, None, Classification.CONFIDENTIAL, True))
    subjects.append(
        Subject(uuid.uuid4(), Role.AUDITOR, "engineering", Classification.RESTRICTED, True)
    )
    return subjects


def _random_resource(rng: random.Random, subjects: list[Subject]) -> Resource:
    # One rule per person or role, because the table allows only one (document, subject) pair.
    rules: dict[tuple[SubjectType, str], AclEntry] = {}
    for _ in range(rng.choice([0, 0, 0, 1, 1, 2])):
        effect = rng.choice(list(AclEffect))
        if rng.random() < 0.6:
            key = (SubjectType.USER, str(rng.choice(subjects).id))
        else:
            key = (SubjectType.ROLE, rng.choice(list(Role)).value)
        rules[key] = AclEntry(key[0], key[1], effect)
    acl = list(rules.values())
    return Resource(
        classification=rng.choice(list(Classification)),
        department=rng.choice(DEPARTMENTS),
        allowed_roles=frozenset(r.value for r in rng.sample(list(Role), rng.randint(0, len(Role)))),
        allowed_purposes=frozenset(
            p.value for p in rng.sample(list(Purpose), rng.randint(0, len(Purpose)))
        ),
        status=rng.choices(list(DocStatus), weights=[6, 1, 1, 1, 1])[0],
        valid_until=rng.choice(VALID_UNTIL),
        acl=tuple(acl),
    )


def _store(db, resource: Resource, index: int, chunks: int) -> uuid.UUID:
    document = Document(
        id=uuid.uuid4(),
        logical_id=uuid.uuid4(),
        version=1,
        filename=f"generated-{index}.txt",
        doc_type="test",
        department=resource.department,
        classification=resource.classification,
        allowed_roles=sorted(resource.allowed_roles),
        allowed_purposes=sorted(resource.allowed_purposes),
        status=resource.status,
        valid_until=resource.valid_until,
        storage_uri="test",
    )
    db.add(document)
    db.flush()
    for rule in resource.acl:
        db.add(
            DocumentACL(
                document_id=document.id,
                subject_type=rule.subject_type,
                subject_id=rule.subject_id,
                effect=rule.effect,
            )
        )
    for number in range(chunks):
        db.add(
            Chunk(
                id=uuid.uuid4(),
                document_id=document.id,
                level="passage",
                chunk_index=number,
                content="text",
                section="s",
                token_count=1,
                classification=resource.classification,
                department=resource.department,
                allowed_roles=sorted(resource.allowed_roles),
                allowed_purposes=sorted(resource.allowed_purposes),
                status=resource.status,
                valid_until=resource.valid_until,
            )
        )
    db.flush()
    return document.id


def test_sql_condition_agrees_with_decide_for_every_user_purpose_and_date(db_session) -> None:
    db_session.execute(delete(Document))  # rolled back at the end; the real data comes back
    subjects = _subjects()
    rng = random.Random(20261116)
    documents: list[tuple[uuid.UUID, Resource]] = []
    for index in range(DOCUMENTS):
        resource = _random_resource(rng, subjects)
        documents.append((_store(db_session, resource, index, rng.choice([1, 1, 2])), resource))

    query = text(f"SELECT DISTINCT ch.document_id FROM chunks ch WHERE {ACCESS_SQL}")
    checked = 0
    for subject, purpose, today in itertools.product(subjects, Purpose, TODAYS):
        rows = db_session.execute(query, access_params(subject, purpose, today))
        allowed_by_sql = {row[0] for row in rows}
        allowed_by_policy = {
            doc_id
            for doc_id, resource in documents
            if decide(subject, resource, purpose, today).allowed
        }
        assert allowed_by_sql == allowed_by_policy, (subject.role, purpose, today)
        checked += 1
    assert checked == len(subjects) * len(Purpose) * len(TODAYS)


def test_the_generated_documents_exercise_every_rule(db_session) -> None:
    """Guards the test above: if the random data stopped covering a rule it would prove less."""
    subjects = _subjects()
    rng = random.Random(20261116)
    resources = [_random_resource(rng, subjects) for _ in range(DOCUMENTS)]
    reasons = {
        decide(subject, resource, purpose, today).reason
        for resource in resources
        for subject, purpose, today in itertools.product(subjects, Purpose, TODAYS)
    }
    assert len(reasons) == 12


def test_unknown_purpose_is_refused() -> None:
    subject = _subjects()[0]
    with pytest.raises(ValueError):
        access_params(subject, "something_else", date(2026, 11, 16))
