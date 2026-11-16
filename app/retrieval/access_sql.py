"""The access rules of app/auth/policy.py, written as one SQL condition on the chunks table.

This is the same decision as `decide()`, made inside the database, so that chunks a user may
not see are never fetched, ranked or returned. tests/integration/test_access_sql_matches_policy.py
checks that the two always agree. If you change a rule in policy.py, change it here too, and
that test will tell you if the two have drifted apart.

The condition expects the chunks table to be aliased as `ch`.
"""

from datetime import date

from app.auth.policy_types import Subject
from app.models.enums import Classification, Purpose, Role

# Rule numbers match the comments in policy.py.
_APPLICABLE_RULE = """
    a.document_id = ch.document_id
    AND ((a.subject_type = 'user' AND a.subject_id = :user_id)
         OR (a.subject_type = 'role' AND a.subject_id = :role))
"""

ACCESS_SQL = f"""
(
    :is_active                                                        -- 1
    AND ch.status = 'active'                                          -- 2
    AND (:purpose <> 'rfp' OR ch.valid_until IS NULL
         OR ch.valid_until >= :today)                                 -- 3
    AND :purpose = ANY(ch.allowed_purposes)                           -- 4
    AND NOT EXISTS (                                                  -- 5
        SELECT 1 FROM document_acl a
        WHERE a.effect = 'deny' AND {_APPLICABLE_RULE}
    )
    AND (
        EXISTS (                                                      -- 6
            SELECT 1 FROM document_acl a
            WHERE a.effect = 'allow' AND {_APPLICABLE_RULE}
        )
        OR COALESCE((
            NOT :is_admin                                             -- 7
            AND ch.classification <> 'restricted'                     -- 8
            AND :role = ANY(ch.allowed_roles)                         -- 9
            AND ch.classification = ANY(:visible_classes)             -- 10
            AND (ch.classification <> 'confidential'                  -- 11
                 OR (ch.department IS NOT NULL
                     AND ch.department = :department))
        ), false)
    )
)
"""


def access_params(subject: Subject, purpose: Purpose | str, today: date) -> dict:
    """The values for ACCESS_SQL. Raises ValueError for a purpose that does not exist."""
    purpose_value = purpose.value if isinstance(purpose, Purpose) else str(purpose)
    if purpose_value not in {p.value for p in Purpose}:
        raise ValueError(f"unknown purpose: {purpose_value!r}")
    return {
        "is_active": subject.is_active,
        "purpose": purpose_value,
        "today": today,
        "user_id": str(subject.id),
        "role": subject.role.value,
        "is_admin": subject.role == Role.ADMIN,
        "visible_classes": [c.value for c in Classification if c.level <= subject.clearance.level],
        "department": subject.department,
    }
