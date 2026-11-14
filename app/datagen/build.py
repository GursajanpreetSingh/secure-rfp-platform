"""Build one manifest document: write the file, count its pages, run the checks."""

from dataclasses import dataclass
from pathlib import Path

from app.datagen import model as m
from app.datagen.docx_writer import write_docx
from app.datagen.pagecount import count_pages
from app.datagen.pdf_writer import write_pdf
from app.datagen.quality import Finding, check_document
from app.datagen.txt_writer import write_txt

_WRITERS = {"pdf": write_pdf, "docx": write_docx, "txt": write_txt}


@dataclass(frozen=True)
class BuildResult:
    doc_id: str
    path: Path
    pages: int
    pages_exact: bool
    minimum_pages: int
    findings: tuple[Finding, ...]

    @property
    def meets_minimum(self) -> bool:
        return self.pages >= self.minimum_pages

    @property
    def ok(self) -> bool:
        return self.meets_minimum and not self.findings


def _format_name(entry) -> str:
    fmt = entry.format
    return str(getattr(fmt, "value", fmt)).lower()


def build_document(entry, doc: m.Document, out_dir: Path, minimum_pages: int) -> BuildResult:
    """Write ``doc`` in the format and filename the manifest entry asks for."""
    fmt = _format_name(entry)
    if fmt not in _WRITERS:
        raise ValueError(f"{entry.id}: unsupported format '{fmt}'")
    path = _WRITERS[fmt](doc, Path(out_dir) / entry.filename)
    counted = count_pages(path)
    return BuildResult(
        doc_id=entry.id,
        path=path,
        pages=counted.pages,
        pages_exact=counted.exact,
        minimum_pages=minimum_pages,
        findings=tuple(check_document(entry.id, doc)),
    )
