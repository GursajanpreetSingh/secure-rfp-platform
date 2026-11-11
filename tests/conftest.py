import pytest
from sqlalchemy.orm import Session

from app.core.db import engine


@pytest.fixture
def db_session():
    """A database session whose changes are always rolled back when the test ends."""
    connection = engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
