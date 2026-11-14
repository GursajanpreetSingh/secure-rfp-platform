"""Render a datagen Document to plain text."""

from pathlib import Path

from app.datagen import model as m


def _table_lines(block: m.Table) -> list[str]:
    rows = [[str(c) for c in block.headers]] + [[str(c) for c in r] for r in block.rows]
    widths = [max(len(r[i]) for r in rows) for i in range(len(block.headers))]

    def fmt(r):
        return " | ".join(c.ljust(w) for c, w in zip(r, widths, strict=True))

    lines = [fmt(rows[0]), "-+-".join("-" * w for w in widths)]
    lines += [fmt(r) for r in rows[1:]]
    if block.caption:
        lines.append(f"({block.caption})")
    return lines


def _render(blocks, prefix: str, level: int, out: list[str]) -> None:
    n = 0
    for b in blocks:
        if isinstance(b, m.Paragraph):
            out += [b.text, ""]
        elif isinstance(b, m.Note):
            out += [f"{b.label.upper()}: {b.text}", ""]
        elif isinstance(b, m.BulletList):
            out += [f"  - {i}" for i in b.items] + [""]
        elif isinstance(b, m.NumberedList):
            out += [f"  {k}. {i}" for k, i in enumerate(b.items, 1)] + [""]
        elif isinstance(b, m.Table):
            out += _table_lines(b) + [""]
        elif isinstance(b, m.PageBreak):
            out += ["", "=" * 70, ""]
        elif isinstance(b, m.Section):
            n += 1
            number = f"{prefix}{n}"
            title = f"{number}. {b.title}"
            out += [title, ("=" if level == 1 else "-") * len(title), ""]
            _render(b.blocks, f"{number}.", level + 1, out)
        else:
            raise TypeError(f"unknown block type: {type(b).__name__}")


def render_txt(doc: m.Document) -> str:
    out = [doc.title.upper(), "=" * len(doc.title), doc.subtitle, ""]
    out += [f"{k}: {v}" for k, v in doc.metadata] + [""]
    _render(doc.sections, "", 1, out)
    return "\n".join(out).rstrip() + "\n"


def write_txt(doc: m.Document, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_txt(doc), encoding="utf-8")
    return path
