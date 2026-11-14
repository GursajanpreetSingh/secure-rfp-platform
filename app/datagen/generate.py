"""Generate the synthetic documents: ``uv run python -m app.datagen.generate``."""

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.datagen.build import BuildResult, build_document
from app.datagen.facts import Facts, load_facts
from app.datagen.registry import Builder, load_all

DEFAULT_OUT_DIR = Path("data/generated")


@dataclass(frozen=True)
class Row:
    doc_id: str
    target_pages: int
    result: BuildResult | None  # None means no builder exists yet


def generate(
    entries: Iterable,
    builders: Mapping[str, Builder],
    facts: Facts,
    out_dir: Path,
    minimum_pages: int,
    only: set[str] | None = None,
) -> list[Row]:
    rows = []
    for entry in entries:
        if only and entry.id not in only:
            continue
        builder = builders.get(entry.id)
        if builder is None:
            rows.append(Row(entry.id, entry.target_pages, None))
            continue
        doc = builder(facts, entry)
        rows.append(
            Row(entry.id, entry.target_pages, build_document(entry, doc, out_dir, minimum_pages))
        )
    return rows


def format_report(rows: list[Row]) -> str:
    lines = [f"{'ID':8} {'target':>6} {'pages':>6}  {'kind':8} status"]
    for row in rows:
        if row.result is None:
            lines.append(f"{row.doc_id:8} {row.target_pages:>6} {'-':>6}  {'-':8} no builder yet")
            continue
        res = row.result
        kind = "exact" if res.pages_exact else "estimate"
        status = "OK" if res.ok else "FAIL"
        lines.append(f"{row.doc_id:8} {row.target_pages:>6} {res.pages:>6}  {kind:8} {status}")
        if not res.meets_minimum:
            lines.append(f"         -> below the {res.minimum_pages}-page minimum")
        lines.extend(f"         -> [{f.kind}] {f.detail}" for f in res.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from app.datagen.manifest import load_manifest

    parser = argparse.ArgumentParser(description="Generate the synthetic documents.")
    parser.add_argument("--only", nargs="*", default=None, help="document ids, e.g. DOC-001")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    manifest = load_manifest()
    docs = manifest.documents
    entries = list(docs.values()) if isinstance(docs, Mapping) else list(docs)
    rows = generate(
        entries,
        load_all(),
        load_facts(),
        args.out,
        manifest.minimum_pages,
        set(args.only) if args.only else None,
    )
    print(format_report(rows))
    return 0 if all(r.result is None or r.result.ok for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
