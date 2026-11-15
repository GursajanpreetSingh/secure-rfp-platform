"""Checks the synthetic corpus (data/raw) and the two RFPs (data/rfps).

Run from the repo root:  uv run python scripts/check_corpus.py
Exit code 0 means every hard check passed.
"""

import re
import sys
from pathlib import Path

import yaml
from docx import Document
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RFPS = ROOT / "data" / "rfps"
GT = RFPS / "ground_truth" / "rfp_ground_truth.yaml"

failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  warn  {msg}")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return squash(" ".join(page.extract_text() or "" for page in PdfReader(str(path)).pages))
    if suffix == ".docx":
        word = Document(str(path))
        cells = [c.text for t in word.tables for r in t.rows for c in r.cells]
        return squash(" ".join([p.text for p in word.paragraphs] + cells))
    return squash(path.read_text(encoding="utf-8"))


# (name, regex, ids where the phrase IS allowed)
RULES = [
    ("subcontractor name", r"NimbusHost|Sentinel Test", set()),
    ("on-premise", r"on[- ]prem", set()),
    ("FedRAMP", r"FedRAMP", set()),
    ("AES-128", r"AES-?128", {"DOC-010"}),
    ("24/7 support", r"24\s*/\s*7|round[- ]the[- ]clock", {"DOC-011"}),
    ("FY25 revenue", r"142(\.0)? crore|INR 142", {"DOC-013"}),
    ("E2 salary band", r"12 to 20 LPA|12-20 LPA", {"DOC-014"}),
    ("stray ** marks", r"\*\*", set()),
]


def check_corpus() -> None:
    print("\n1. Corpus files (data/raw)")
    manifest = yaml.safe_load((ROOT / "data" / "manifest.yaml").read_text(encoding="utf-8"))
    minimum = manifest["minimum_pages"]
    texts: dict[str, str] = {}
    for doc in manifest["documents"]:
        doc_id, name, fmt = doc["id"], doc["filename"], doc["format"]
        path = RAW / name
        if not path.exists():
            fail(f"{doc_id}: missing file {name}")
            continue
        if fmt == "pdf":
            pages = len(PdfReader(str(path)).pages)
            text = read_text(path)
            if doc_id == "DOC-009":
                if len(text) < 50:
                    ok(f"{doc_id}: {pages} pages, scanned (no text layer), as designed")
                else:
                    fail(f"{doc_id}: has a text layer, but it should be a scan")
                if pages < minimum:
                    fail(f"{doc_id}: {pages} pages, need {minimum}")
                continue
            (ok if pages >= minimum else fail)(f"{doc_id}: {pages} pages (need {minimum})")
            texts[doc_id] = text
        elif fmt == "docx":
            text = read_text(path)
            words = len(text.split())
            texts[doc_id] = text
            if words >= 4500:
                ok(f"{doc_id}: opens, {words} words (tables are dense; confirm 20+ pages in Word)")
            else:
                warn(f"{doc_id}: only {words} words, check the page count in Word")
        else:
            text = path.read_text(encoding="utf-8")
            words = len(text.split())
            texts[doc_id] = squash(text)
            (ok if words >= minimum * 500 else fail)(
                f"{doc_id}: {words} words (need {minimum * 500})"
            )

    print("\n2. Forbidden or restricted phrases")
    clean = True
    for doc_id, text in texts.items():
        for name, pattern, allowed in RULES:
            if re.search(pattern, text, re.IGNORECASE) and doc_id not in allowed:
                fail(f"{doc_id}: contains {name}")
                clean = False
    if clean:
        ok("no forbidden phrase outside its allowed document")
    for doc_id, pattern, label in [
        ("DOC-010", r"AES-?128", "AES-128 claim"),
        ("DOC-011", r"24\s*/\s*7", "24/7 draft claim"),
        ("DOC-013", r"142", "revenue figure"),
        ("DOC-008", r"administrators only|administrators", "old MFA rule"),
        ("DOC-007", r"ignore all earlier instructions", "prompt-injection paragraph"),
    ]:
        if doc_id in texts and re.search(pattern, texts[doc_id], re.IGNORECASE):
            ok(f"{doc_id}: trap present ({label})")
        else:
            fail(f"{doc_id}: expected trap missing ({label})")


def check_rfps() -> None:
    print("\n3. RFPs and ground truth (data/rfps)")
    if not GT.exists():
        fail(f"missing {GT.relative_to(ROOT)}")
        return
    truth = yaml.safe_load(GT.read_text(encoding="utf-8"))
    pdfs = {
        "RFP-A": next(RFPS.glob("RFP-A_*.pdf"), None),
        "RFP-B": next(RFPS.glob("RFP-B_*.pdf"), None),
    }
    expected_counts = {"RFP-A": 29, "RFP-B": 40}
    allowed = {"compliant", "partial", "non_compliant", "insufficient_evidence"}
    for rfp in truth["rfps"]:
        name = rfp["rfp"]
        reqs = rfp["requirements"]
        (ok if len(reqs) == expected_counts[name] else fail)(
            f"{name}: {len(reqs)} requirements (expected {expected_counts[name]})"
        )
        ids = [r["id"] for r in reqs]
        (ok if len(ids) == len(set(ids)) else fail)(f"{name}: requirement IDs are unique")
        bad = [r["id"] for r in reqs if r["expected_status"] not in allowed]
        (ok if not bad else fail)(f"{name}: all statuses are valid {bad or ''}")
        pdf = pdfs[name]
        if pdf is None:
            fail(f"{name}: PDF missing")
            continue
        text = read_text(pdf)
        missing = [
            r["id"] for r in reqs if r["id"] not in text or squash(r["text"])[:25] not in text
        ]
        (ok if not missing else fail)(f"{name}: every requirement found in the PDF {missing or ''}")
    if "ignore any contradicting documents" in read_text(pdfs["RFP-B"]):
        ok("RFP-B: hostile instruction present, as designed")
    else:
        fail("RFP-B: hostile instruction missing")


if __name__ == "__main__":
    check_corpus()
    check_rfps()
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"All hard checks passed ({len(warnings)} warning(s)).")
