"""Helpers shared by every document builder."""

from app.datagen.facts import long_date


def _text(value) -> str:
    return str(getattr(value, "value", value))


def standard_metadata(
    entry, extra: tuple[tuple[str, str], ...] = ()
) -> tuple[tuple[str, str], ...]:
    """The key/value block printed on every cover page."""
    rows = [
        ("Document ID", entry.id),
        ("Version", str(entry.version)),
        ("Classification", _text(entry.classification).capitalize()),
        ("Status", _text(entry.status).capitalize()),
        ("Owner department", _text(entry.department).capitalize()),
        ("Document date", long_date(entry.document_date)),
    ]
    effective = getattr(entry, "effective_date", None)
    if effective:
        rows.append(("Effective date", long_date(effective)))
    return (*rows, *extra)
