"""Copy a document's access rules onto each of its chunks.

Search will filter on the chunk's own copy of the rules, so a chunk must never be less
restrictive than its document. The only way to build chunk rows here is from the document's
`Resource`, which makes it hard to forget a field.

The explicit allow and deny rules (the ACL) stay on the document. A chunk finds them through
its `document_id`, so changing a rule never needs a rewrite of every chunk.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.auth.policy_types import AclEntry, Resource
from app.ingestion.chunk import ChunkDraft
from app.models.enums import Classification, DocStatus


@dataclass(frozen=True)
class ChunkRow:
    """One row for the `chunks` table, before the embedding is added."""

    id: uuid.UUID
    document_id: uuid.UUID
    parent_id: uuid.UUID | None
    level: str
    chunk_index: int
    content: str
    page: int | None
    section: str
    token_count: int
    from_ocr: bool
    # Access fields, copied from the document:
    classification: Classification
    department: str | None
    allowed_roles: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    status: DocStatus
    valid_until: date | None


def build_chunk_rows(
    document_id: uuid.UUID,
    resource: Resource,
    drafts: list[ChunkDraft],
    new_id: Callable[[], uuid.UUID] = uuid.uuid4,
) -> list[ChunkRow]:
    """Turn drafts into rows. Every row carries the document's access fields."""
    ids = {draft.key: new_id() for draft in drafts}
    rows = []
    for draft in drafts:
        parent_id = None
        if draft.parent_key is not None:
            if draft.parent_key not in ids:
                raise ValueError(f"chunk {draft.key} points at a missing parent")
            parent_id = ids[draft.parent_key]
        rows.append(
            ChunkRow(
                id=ids[draft.key],
                document_id=document_id,
                parent_id=parent_id,
                level=draft.level,
                chunk_index=draft.chunk_index,
                content=draft.content,
                page=draft.page,
                section=draft.section,
                token_count=draft.token_count,
                from_ocr=draft.from_ocr,
                classification=resource.classification,
                department=resource.department,
                allowed_roles=tuple(sorted(resource.allowed_roles)),
                allowed_purposes=tuple(sorted(resource.allowed_purposes)),
                status=resource.status,
                valid_until=resource.valid_until,
            )
        )
    return rows


def chunk_resource(row: ChunkRow, acl: tuple[AclEntry, ...]) -> Resource:
    """The access rules as seen from a chunk: its own copy plus its document's ACL."""
    return Resource(
        classification=row.classification,
        department=row.department,
        allowed_roles=frozenset(row.allowed_roles),
        allowed_purposes=frozenset(row.allowed_purposes),
        status=row.status,
        valid_until=row.valid_until,
        acl=acl,
    )
