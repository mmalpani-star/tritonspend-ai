"""Unexpected server errors must reach the browser as a readable JSON 500 with CORS headers.

Without CORS headers the browser hides the response and the app shows "Couldn't reach
TritonSpend", which is how a missing table (an unapplied migration) looked in the UI.
"""

from fastapi.testclient import TestClient

from backend.app.db import get_db
from backend.app.main import app

ORIGIN = "http://localhost:3000"


def _broken_db():
    raise RuntimeError("simulated: no such table")
    yield  # pragma: no cover - makes this a generator dependency like get_db


def test_unhandled_errors_are_json_500s_with_cors_headers():
    app.dependency_overrides[get_db] = _broken_db
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/v1/food/venues", headers={"Origin": ORIGIN})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}  # no internals leaked
    assert response.headers.get("access-control-allow-origin") == ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_health_endpoint_is_a_database_free_liveness_probe():
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
