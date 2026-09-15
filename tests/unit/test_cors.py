"""Tests for CORS configuration on the application instance.

The allowed origins come from the ``CORS_ORIGINS`` setting, whose defaults are the
local Vite development servers.
"""

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

LOCALHOST_ORIGIN = "http://localhost:5173"
LOOPBACK_ORIGIN = "http://127.0.0.1:5173"
UNLISTED_ORIGIN = "https://unlisted.example.com"


def test_preflight_allows_localhost_dev_origin() -> None:
    """A preflight request from the Vite dev server is allowed."""
    response = client.options(
        "/health",
        headers={
            "Origin": LOCALHOST_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOCALHOST_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_preflight_allows_loopback_dev_origin() -> None:
    """The ``127.0.0.1`` form of the Vite dev server origin is allowed too."""
    response = client.options(
        "/health",
        headers={
            "Origin": LOOPBACK_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == LOOPBACK_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_simple_request_from_dev_origin_is_allowed_and_unchanged() -> None:
    """A normal request carries CORS headers and keeps the health payload intact."""
    response = client.get("/health", headers={"Origin": LOCALHOST_ORIGIN})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == LOCALHOST_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unlisted_origin_is_not_allowed() -> None:
    """Origins outside the configured list receive no CORS allow header."""
    response = client.get("/health", headers={"Origin": UNLISTED_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
