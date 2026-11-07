from enum import StrEnum

_CLASSIFICATION_ORDER = ("public", "internal", "confidential", "restricted")


class Role(StrEnum):
    ADMIN = "admin"
    EXECUTIVE = "executive"
    EMPLOYEE = "employee"
    AUDITOR = "auditor"
    EXTERNAL = "external"


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @property
    def level(self) -> int:
        """0 = public ... 3 = restricted. Used to compare clearance with classification."""
        return _CLASSIFICATION_ORDER.index(self.value)


class DocStatus(StrEnum):
    ACTIVE = "active"
    DRAFT = "draft"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    PARSE_FAILED = "parse_failed"


class Purpose(StrEnum):
    RFP = "rfp"
    ENTERPRISE_QA = "enterprise_qa"


class AclEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class SubjectType(StrEnum):
    USER = "user"
    ROLE = "role"


class AuditDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ERROR = "error"
    INFO = "info"
