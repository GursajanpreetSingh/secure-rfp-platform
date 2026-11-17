"""Small pure helpers for the screens: labels, safe text, filters and the review checks.

Nothing here touches Streamlit or the network, so all of it is unit tested.
"""

from __future__ import annotations

import re
from datetime import datetime

STATUS_ORDER = ["compliant", "partial", "non_compliant", "insufficient_evidence", "not_judged"]
STATUS_LABEL = {
    "compliant": "Compliant",
    "partial": "Partial",
    "non_compliant": "Non-compliant",
    "insufficient_evidence": "Insufficient evidence",
    "not_judged": "Not judged",
}
STATUS_ICON = {
    "compliant": "🟢",
    "partial": "🟡",
    "non_compliant": "🔴",
    "insufficient_evidence": "⚪",
    "not_judged": "⚫",
}
REVIEW_LABEL = {
    "pending": "Waiting for review",
    "approved": "Approved",
    "edited": "Edited",
    "rejected": "Rejected",
}
MIN_NOTE_CHARS = 10  # the same minimum the server enforces
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
UPLOAD_TYPES = ["pdf", "docx", "txt"]

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$&:])")


def md_escape(text: object) -> str:
    """Make text safe to place inside a markdown label. Text from documents is never trusted."""
    flat = " ".join(str(text if text is not None else "").split())
    return _MARKDOWN_SPECIAL.sub(r"\\\1", flat)


def status_text(status: str | None) -> str:
    if not status:
        return "-"
    return f"{STATUS_ICON.get(status, '')} {STATUS_LABEL.get(status, status)}".strip()


def short_time(value: str | None) -> str:
    if not value:
        return "-"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "-"
    return moment.strftime("%Y-%m-%d %H:%M") + " UTC"


def chart_rows(status_counts: dict[str, int]) -> dict[str, int]:
    """Counts in a fixed, readable order, with the friendly names. Unknown statuses are skipped."""
    return {
        STATUS_LABEL[s]: int(status_counts.get(s, 0)) for s in STATUS_ORDER if status_counts.get(s)
    }


def progress_fraction(answered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, answered / total))


def newest_first(runs: list[dict]) -> list[dict]:
    return sorted(runs, key=lambda run: run.get("created_at") or "", reverse=True)


def any_running(runs: list[dict]) -> bool:
    return any(run.get("state") == "running" for run in runs)


def filter_results(
    results: list[dict], review_state: str | None = None, status: str | None = None
) -> list[dict]:
    """Keep results that match the chosen review state and the status shown to the reader.

    The status shown is the reviewer's choice once reviewed, otherwise the system's.
    """
    kept = []
    for result in results:
        if review_state and result["review_state"] != review_state:
            continue
        if status and shown_status(result) != status:
            continue
        kept.append(result)
    return sorted(kept, key=lambda r: r["position"])


def shown_status(result: dict) -> str | None:
    if result["review_state"] in ("approved", "edited"):
        return result["final_status"]
    if result["review_state"] == "rejected":
        return None
    return result["ai_status"]


def allowed_actions(result: dict) -> list[str]:
    """The system's own 'not judged' answer cannot be approved, only edited or rejected."""
    actions = ["approve", "edit", "reject"]
    if result["ai_status"] == "not_judged":
        actions.remove("approve")
    return actions


def review_problem(action: str, final_status: str | None, note: str) -> str | None:
    """The same checks the server makes, so people hear about a mistake before sending."""
    note = (note or "").strip()
    if action == "edit" and not final_status:
        return "Choose the status you want to use."
    if action in ("edit", "reject") and len(note) < MIN_NOTE_CHARS:
        return f"Say why in a note of at least {MIN_NOTE_CHARS} characters."
    return None


def upload_problem(filename: str, size: int) -> str | None:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in UPLOAD_TYPES:
        return "Use a PDF, DOCX or TXT file."
    if size <= 0:
        return "The file is empty."
    if size > MAX_UPLOAD_BYTES:
        return "The file is larger than 10 MB."
    return None
