"""Read the requirements out of a tender document.

Two layouts are understood, because they are the two ways tenders number their requirements:
  * table rows that start with an ID cell:   ID: A-001 | Requirement: ... | Priority: ...
  * numbered list items:                      B-033 (Mandatory). The vendor shall ...
Only items that carry an ID are requirements. Other sentences with "shall", such as duties of
the buyer or general contract terms, are left out on purpose.

Text that tries to give orders to an AI system is collected separately (see guard.py) and
never becomes a requirement.
"""

import re
from dataclasses import dataclass

from app.ingestion.extract import ExtractedDocument
from app.rfp.guard import Suspicious, reasons_for, scan

ID_PATTERN = r"[A-Z]{1,6}-\d{1,4}"
LIST_ITEM = re.compile(rf"^(?P<id>{ID_PATTERN}) \((?P<priority>[A-Za-z ]+)\)\.? ?(?P<text>.*)$")
TABLE_ROW = re.compile(rf"^(?:ID|Ref|Req(?:uirement)? ?ID): ?(?P<id>{ID_PATTERN}) \| ")
HEADING = re.compile(r"^#+ (?P<title>.+)$")
CAPTION = re.compile(r"^Table \d+\.")
SECTION_NUMBER = re.compile(r"^\d+(\.\d+)*\.?\s*")
TEXT_LABELS = ("requirement", "description", "requirement description")
PRIORITY_LABELS = ("priority", "type", "level")
MANDATORY = {"mandatory", "must", "required", "essential", "shall"}
DESIRABLE = {"desirable", "should", "optional", "preferred", "nice to have", "may"}


@dataclass(frozen=True)
class Requirement:
    id: str
    section: str
    priority: str  # "mandatory" or "desirable"
    text: str
    page: int | None
    flagged: bool = False  # the text itself looks like an instruction to an AI system


@dataclass(frozen=True)
class ParsedRfp:
    requirements: tuple[Requirement, ...]
    suspicious: tuple[Suspicious, ...]
    warnings: tuple[str, ...]


def _priority(raw: str, requirement_id: str, warnings: list[str]) -> str:
    word = raw.strip().lower()
    if word in MANDATORY:
        return "mandatory"
    if word in DESIRABLE:
        return "desirable"
    warnings.append(f"{requirement_id}: unknown priority {raw!r}, treated as mandatory")
    return "mandatory"  # the stricter reading is the safe one


def _table_fields(line: str) -> dict[str, str]:
    fields = {}
    for cell in line.split(" | "):
        label, _, value = cell.partition(": ")
        fields[label.strip().lower()] = value.strip()
    return fields


def parse_rfp(document: ExtractedDocument) -> ParsedRfp:
    requirements: list[Requirement] = []
    suspicious: list[Suspicious] = []
    warnings: list[str] = []
    seen: set[str] = set()
    section = ""
    open_item: dict | None = None  # a list item that may continue on the next line
    loose: list[tuple[int | None, str]] = []  # lines that are not requirements

    def close_item() -> None:
        nonlocal open_item
        if open_item is None:
            return
        text = " ".join(open_item["text"].split())
        _add(open_item["id"], open_item["section"], open_item["priority"], text, open_item["page"])
        open_item = None

    def flush_loose() -> None:
        if loose:
            page = loose[0][0]
            suspicious.extend(scan(section, " ".join(text for _, text in loose), page))
            loose.clear()

    def _add(req_id: str, sec: str, priority_raw: str, text: str, page: int | None) -> None:
        if req_id in seen:
            warnings.append(f"{req_id}: appears more than once, only the first is kept")
            return
        if not text:
            warnings.append(f"{req_id}: has no requirement text, skipped")
            return
        seen.add(req_id)
        priority = _priority(priority_raw, req_id, warnings)
        flagged = bool(reasons_for(text))
        if flagged:
            suspicious.extend(scan(sec, text, page))
        requirements.append(Requirement(req_id, sec, priority, text, page, flagged))

    for page in document.pages:
        for line in page.text.splitlines():
            heading = HEADING.match(line)
            if heading:
                close_item()
                flush_loose()
                title = heading.group("title")
                section = SECTION_NUMBER.sub("", title).strip() or section
                suspicious.extend(scan(section, title, page.number))
                continue
            if CAPTION.match(line):
                close_item()
                continue
            item = LIST_ITEM.match(line)
            if item:
                close_item()
                flush_loose()
                open_item = {
                    "id": item.group("id"),
                    "section": section,
                    "priority": item.group("priority"),
                    "text": item.group("text"),
                    "page": page.number,
                }
                continue
            row = TABLE_ROW.match(line)
            if row:
                close_item()
                flush_loose()
                fields = _table_fields(line)
                text = next((fields[k] for k in TEXT_LABELS if k in fields), "")
                priority = next((fields[k] for k in PRIORITY_LABELS if k in fields), "")
                _add(row.group("id"), section, priority, text, page.number)
                continue
            if open_item is not None:
                open_item["text"] += " " + line
                continue
            loose.append((page.number, line))
    close_item()
    flush_loose()
    return ParsedRfp(tuple(requirements), tuple(suspicious), tuple(warnings))
