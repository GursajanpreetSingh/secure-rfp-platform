import pytest
from fastapi.testclient import TestClient

from app.api.main import app

pytestmark = pytest.mark.integration


def test_health_ok_with_real_database():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True}
