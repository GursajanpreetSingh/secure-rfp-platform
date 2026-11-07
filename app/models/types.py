from enum import Enum

from sqlalchemy import Enum as SAEnum


def db_enum(enum_cls: type[Enum]) -> SAEnum:
    """Store enum VALUES (e.g. 'employee') as text, with a CHECK constraint."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )
