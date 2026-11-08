import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.main import app
from app.core.db import get_db


class BrokenSession:
    """A stand-in database session whose queries always fail."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("secret connection detail"))


@pytest.fixture
def client_with_broken_db():
    app.dependency_overrides[get_db] = lambda: BrokenSession()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_reports_503_when_db_is_down(client_with_broken_db):
    response = client_with_broken_db.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": False}


def test_health_error_does_not_leak_details(client_with_broken_db):
    response = client_with_broken_db.get("/health")
    assert "secret connection detail" not in response.text
