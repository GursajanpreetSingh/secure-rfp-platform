"""Registry of document builders. Each builder turns facts + a manifest entry into a Document."""

import importlib
import pkgutil
from collections.abc import Callable

from app.datagen import model as m
from app.datagen.facts import Facts

Builder = Callable[[Facts, object], m.Document]

BUILDERS: dict[str, Builder] = {}


def register(doc_id: str) -> Callable[[Builder], Builder]:
    """Decorator: ``@register("DOC-001")`` on a function ``build(facts, entry)``."""

    def decorator(func: Builder) -> Builder:
        if doc_id in BUILDERS:
            raise ValueError(f"duplicate builder for {doc_id}")
        BUILDERS[doc_id] = func
        return func

    return decorator


def load_all() -> dict[str, Builder]:
    """Import every module under app.datagen.docs so its builders register themselves."""
    from app.datagen import docs

    for info in pkgutil.iter_modules(docs.__path__):
        importlib.import_module(f"{docs.__name__}.{info.name}")
    return BUILDERS
