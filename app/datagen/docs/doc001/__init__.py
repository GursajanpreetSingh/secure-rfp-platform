"""DOC-001 Information Security Policy (v2). Parts are added one at a time."""

from app.datagen import model as m
from app.datagen.common import standard_metadata
from app.datagen.docs.doc001 import part1, part2
from app.datagen.facts import Facts
from app.datagen.registry import register


@register("DOC-001")
def build(facts: Facts, entry) -> m.Document:
    reg = facts.get("policy_register.information_security_policy")
    sections = (*part1.sections(facts, entry), *part2.sections(facts, entry))
    return m.Document(
        title=entry.title,
        subtitle=f"{facts.get('company.name')} - {reg['document_number']}",
        metadata=standard_metadata(
            entry,
            extra=(
                ("Document number", reg["document_number"]),
                ("Policy owner", reg["owner"]),
            ),
        ),
        sections=sections,
    )
