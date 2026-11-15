import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from app.auth.policy_types import AclEntry, Resource
from app.models.enums import AclEffect, Classification, DocStatus, Purpose, Role, SubjectType

MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "manifest.yaml"

REQUIRED_KEYS = {
    "id",
    "title",
    "logical_key",
    "version",
    "filename",
    "format",
    "target_pages",
    "document_type",
    "department",
    "classification",
    "allowed_roles",
    "allowed_purposes",
    "status",
    "document_date",
    "facts",
}
OPTIONAL_KEYS = {"effective_date", "superseded_on", "valid_until", "acl"}
FORMATS = {"pdf", "docx", "txt"}


@dataclass(frozen=True)
class ManifestAcl:
    effect: AclEffect
    subject_type: SubjectType
    subject: str  # a user's email address, or a role name


@dataclass(frozen=True)
class ManifestEntry:
    id: str
    title: str
    logical_key: str
    version: int
    filename: str
    format: str
    target_pages: int
    document_type: str
    department: str | None
    classification: Classification
    allowed_roles: frozenset[str]
    allowed_purposes: frozenset[str]
    status: DocStatus
    document_date: date
    effective_date: date | None
    superseded_on: date | None
    valid_until: date | None
    acl: tuple[ManifestAcl, ...]
    facts: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    minimum_pages: int
    documents: tuple[ManifestEntry, ...]


def _optional_date(raw: dict, key: str) -> date | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, date):
        raise ValueError(f"{raw['id']}: {key} must be a date like 2025-01-31")
    return value


def _parse_acl(raw_rule: dict, label: str) -> ManifestAcl:
    rule = ManifestAcl(
        effect=AclEffect(raw_rule["effect"]),
        subject_type=SubjectType(raw_rule["subject_type"]),
        subject=str(raw_rule["subject"]),
    )
    if rule.subject_type == SubjectType.ROLE:
        Role(rule.subject)
    return rule


def _parse_entry(raw: dict) -> ManifestEntry:
    if not isinstance(raw, dict):
        raise ValueError("each manifest entry must be a mapping")
    label = raw.get("id", "<no id>")
    missing = REQUIRED_KEYS - set(raw)
    unknown = set(raw) - REQUIRED_KEYS - OPTIONAL_KEYS
    if missing:
        raise ValueError(f"{label}: missing keys {sorted(missing)}")
    if unknown:
        raise ValueError(f"{label}: unknown keys {sorted(unknown)}")
    if raw["format"] not in FORMATS:
        raise ValueError(f"{label}: format must be one of {sorted(FORMATS)}")
    if not isinstance(raw["version"], int) or raw["version"] < 1:
        raise ValueError(f"{label}: version must be a whole number of at least 1")
    if not isinstance(raw["target_pages"], int) or raw["target_pages"] < 1:
        raise ValueError(f"{label}: target_pages must be a positive whole number")
    if not isinstance(raw["document_date"], date):
        raise ValueError(f"{label}: document_date must be a date like 2025-01-31")

    return ManifestEntry(
        id=str(raw["id"]),
        title=str(raw["title"]),
        logical_key=str(raw["logical_key"]),
        version=raw["version"],
        filename=str(raw["filename"]),
        format=raw["format"],
        target_pages=raw["target_pages"],
        document_type=str(raw["document_type"]),
        department=raw["department"],
        classification=Classification(raw["classification"]),
        allowed_roles=frozenset(Role(r).value for r in raw["allowed_roles"]),
        allowed_purposes=frozenset(Purpose(p).value for p in raw["allowed_purposes"]),
        status=DocStatus(raw["status"]),
        document_date=raw["document_date"],
        effective_date=_optional_date(raw, "effective_date"),
        superseded_on=_optional_date(raw, "superseded_on"),
        valid_until=_optional_date(raw, "valid_until"),
        acl=tuple(_parse_acl(r, str(label)) for r in raw.get("acl") or []),
        facts=tuple(str(f) for f in raw["facts"]),
    )


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    """Read and strictly validate the manifest. Any mistake raises ValueError."""
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or not isinstance(raw.get("documents"), list):
        raise ValueError("manifest must contain a 'documents' list")
    if not isinstance(raw.get("minimum_pages"), int):
        raise ValueError("manifest must contain a whole-number 'minimum_pages'")

    entries = tuple(_parse_entry(item) for item in raw["documents"])
    for field in ("id", "filename"):
        values = [getattr(e, field) for e in entries]
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {field} in manifest")
    return Manifest(minimum_pages=raw["minimum_pages"], documents=entries)


def to_resource(entry: ManifestEntry, user_ids: dict[str, uuid.UUID]) -> Resource:
    """Turn a manifest entry into the record the policy function works with."""
    rules = []
    for rule in entry.acl:
        if rule.subject_type == SubjectType.USER:
            subject_id = str(user_ids[rule.subject])
        else:
            subject_id = rule.subject
        rules.append(AclEntry(rule.subject_type, subject_id, rule.effect))
    return Resource(
        classification=entry.classification,
        department=entry.department,
        allowed_roles=entry.allowed_roles,
        allowed_purposes=entry.allowed_purposes,
        status=entry.status,
        valid_until=entry.valid_until,
        acl=tuple(rules),
    )
