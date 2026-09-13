"""Foundation test: the health endpoint must return a successful response."""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_returns_ok() -> None:
    """``GET /health`` returns 200 with a healthy payload."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
