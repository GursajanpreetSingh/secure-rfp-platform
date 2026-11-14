"""Typed-ish access to data/company_facts.yaml, the source of truth for every document."""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

FACTS_PATH = Path(__file__).resolve().parents[2] / "data" / "company_facts.yaml"


class Facts:
    """Read-only view over the facts file with dotted-path lookup.

    ``facts.get("security.patch_sla_days.critical")`` -> 7
    Lists can be indexed by position (``certifications.0.name``) or by the ``id`` of an
    entry (``certifications.CERT-ISO27001.expires``).
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get(self, path: str) -> Any:
        node: Any = self._data
        for part in path.split("."):
            node = self._step(node, part, path)
        return node

    @staticmethod
    def _step(node: Any, part: str, path: str) -> Any:
        if isinstance(node, dict) and part in node:
            return node[part]
        if isinstance(node, list):
            if part.isdigit() and int(part) < len(node):
                return node[int(part)]
            for item in node:
                if isinstance(item, dict) and item.get("id") == part:
                    return item
        raise KeyError(f"fact path not found: {path} (stuck at '{part}')")

    def __getitem__(self, path: str) -> Any:
        return self.get(path)

    @property
    def as_of(self) -> date:
        return self.get("as_of_date")


@lru_cache(maxsize=1)
def load_facts(path: Path = FACTS_PATH) -> Facts:
    with Path(path).open(encoding="utf-8") as handle:
        return Facts(yaml.safe_load(handle))


def long_date(value: date) -> str:
    """15 March 2026 (no platform-specific strftime flags, so it works on Windows)."""
    return f"{value.day} {value:%B %Y}"
