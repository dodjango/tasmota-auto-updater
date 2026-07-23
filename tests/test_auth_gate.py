"""Integration tests for the /api/* access-control gate (Phase 1).

Exercises the fail-closed gate via the Flask test client: no auth → 401,
UI session cookie → allowed, X-API-Key → allowed, non-JSON state change → 415.
"""
import pytest

from server import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, DEVICES_FILE="devices-dev.yaml")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_api_blocked_without_session_or_key(client):
    """No UI session and no API key → 401."""
    resp = client.post("/api/update/all", json={"check_only": True})
    assert resp.status_code == 401


def test_ui_session_grants_api_access(client):
    """GET / establishes the signed session cookie; /api/* is then allowed."""
    client.get("/")  # sets the ui_authenticated session cookie
    resp = client.get("/api/devices")
    assert resp.status_code == 200


def test_state_change_requires_json(client):
    """A non-JSON POST to a state-changing endpoint is rejected (CSRF hardening)."""
    client.get("/")  # authenticated UI session
    resp = client.post("/api/update/all", data="check_only=true",
                       content_type="application/x-www-form-urlencoded")
    assert resp.status_code == 415


def test_health_and_version_not_gated(client):
    """Operational endpoints stay open (container healthcheck, version)."""
    assert client.get("/health").status_code == 200
    assert client.get("/version").status_code == 200


def test_api_key_client(monkeypatch):
    """With API_KEY set, a valid X-API-Key is accepted and a wrong/absent one is not."""
    monkeypatch.setenv("API_KEY", "s3cret-test-key")
    app = create_app()
    app.config.update(TESTING=True, DEVICES_FILE="devices-dev.yaml")
    client = app.test_client()

    assert client.get("/api/devices",
                      headers={"X-API-Key": "s3cret-test-key"}).status_code == 200
    assert client.get("/api/devices",
                      headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/devices").status_code == 401
