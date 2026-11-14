"""Quality checks for generated documents.

Two kinds of check, both returning a list of Findings (empty means clean):

* claim rules: phrases that would contradict company_facts.yaml, allowed only in the
  documents that are *supposed* to contain them (the deliberate traps);
* repetition limits: stops the generator padding pages with copy-pasted text.
"""

import re
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.datagen import model as m

MIN_WORDS_FOR_REPETITION = 8  # shorter lines ("Yes", "See section 3") may repeat freely
MAX_REPEATS_PER_DOCUMENT = 2
MAX_REPEATS_ACROSS_SET = 3


@dataclass(frozen=True)
class Finding:
    kind: str
    doc_id: str
    detail: str


@dataclass(frozen=True)
class ClaimRule:
    name: str
    pattern: re.Pattern[str]
    allowed_doc_ids: frozenset[str]
    reason: str


def _rule(name: str, pattern: str, allowed: set[str], reason: str) -> ClaimRule:
    return ClaimRule(name, re.compile(pattern, re.IGNORECASE), frozenset(allowed), reason)


# Extend this table as the facts grow. Each rule names where the phrase IS allowed.
DEFAULT_RULES: tuple[ClaimRule, ...] = (
    _rule(
        "24x7-support",
        r"24\s*/\s*7\s+(?:customer\s+|technical\s+)?support|round[- ]the[- ]clock\s+support",
        {"DOC-011"},
        "support is Monday-Friday; only the draft expansion proposal promises 24/7",
    ),
    _rule(
        "aes-128",
        r"AES[- ]?128",
        {"DOC-010"},
        "current encryption is AES-256; AES-128 appears only in the superseded 2022 guide",
    ),
    _rule(
        "on-premise",
        r"on[- ]prem(?:ise|ises)?\b",
        set(),
        "on-premise deployment is documented nowhere (the RFP answer is insufficient_evidence)",
    ),
    _rule(
        "iso9001-valid",
        r"ISO\s*9001[^.\n]{0,80}\b(?:valid|current|in force)\b",
        {"DOC-009"},
        "the ISO 9001 certificate expired on 2024-12-31",
    ),
)


def _units(blocks) -> Iterator[str]:
    """Yield every piece of prose in a block tree, depth first."""
    for b in blocks:
        if isinstance(b, m.Paragraph):
            yield b.text
        elif isinstance(b, m.Note):
            yield b.text
        elif isinstance(b, (m.BulletList, m.NumberedList)):
            yield from b.items
        elif isinstance(b, m.Table):
            for row in b.rows:
                yield from (str(c) for c in row)
        elif isinstance(b, m.Section):
            yield b.title
            yield from _units(b.blocks)


def prose_units(doc: m.Document) -> list[str]:
    return [doc.title, doc.subtitle, *_units(doc.sections)]


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _repeatable_units(doc: m.Document) -> list[str]:
    units = (_normalise(u) for u in prose_units(doc))
    return [u for u in units if len(u.split()) >= MIN_WORDS_FOR_REPETITION]


def check_claims(
    doc_id: str, doc: m.Document, rules: tuple[ClaimRule, ...] = DEFAULT_RULES
) -> list[Finding]:
    findings = []
    for rule in rules:
        if doc_id in rule.allowed_doc_ids:
            continue
        for unit in prose_units(doc):
            match = rule.pattern.search(unit)
            if match:
                findings.append(
                    Finding("claim", doc_id, f"{rule.name}: '{match.group(0)}' - {rule.reason}")
                )
    return findings


def check_repetition(
    doc_id: str, doc: m.Document, max_repeats: int = MAX_REPEATS_PER_DOCUMENT
) -> list[Finding]:
    counts = Counter(_repeatable_units(doc))
    return [
        Finding("repetition", doc_id, f"{n} copies of: {text[:70]}...")
        for text, n in sorted(counts.items())
        if n > max_repeats
    ]


def check_document(doc_id: str, doc: m.Document) -> list[Finding]:
    return check_claims(doc_id, doc) + check_repetition(doc_id, doc)


def check_set_repetition(
    docs: Mapping[str, m.Document], max_total: int = MAX_REPEATS_ACROSS_SET
) -> list[Finding]:
    total: Counter[str] = Counter()
    for doc in docs.values():
        total.update(_repeatable_units(doc))
    return [
        Finding("set-repetition", "*", f"{n} copies across the set: {text[:70]}...")
        for text, n in sorted(total.items())
        if n > max_total
    ]
