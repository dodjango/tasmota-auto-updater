"""Integration tests: async batch jobs via the API (Phase 2).

The updater is monkeypatched to a fast stub so these stay deterministic and
offline (no GitHub release lookup / device I/O).
"""
import time

import pytest

from server import create_app
from app.tasmota import jobs


@pytest.fixture
def client(monkeypatch):
    jobs._reset_for_tests()

    def fast_updater(config, check_only=False):
        return {"ip": config["ip"], "success": True, "needs_update": True,
                "message": "stub", "current_version": "1.0", "latest_version": "1.1"}

    monkeypatch.setattr("app.tasmota.jobs.update_device_firmware", fast_updater)

    app = create_app()
    app.config.update(TESTING=True, DEVICES_FILE="devices-dev.yaml")
    c = app.test_client()
    c.get("/")  # establish the authenticated UI session (Phase 1 gate)
    yield c
    jobs._reset_for_tests()


def _wait_for_job(client, job_id, timeout=15.0):
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").get_json()
        if job["status"] in ("completed", "error"):
            return job
        time.sleep(0.05)
    return job


def test_batch_update_returns_202_and_completes(client):
    resp = client.post("/api/update/all", json={"check_only": False, "update_only_needed": True})
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]

    job = _wait_for_job(client, job_id)
    assert job["status"] == "completed"
    assert job["total"] >= 1
    assert len(job["results"]) == job["total"]
    assert job["summary"]["updated"] == job["total"]


def test_second_batch_while_running_conflicts(client, monkeypatch):
    # Make the updater slow so the first job stays 'running'.
    import threading
    release = threading.Event()

    def slow_updater(config, check_only=False):
        release.wait(timeout=5)
        return {"ip": config["ip"], "success": True, "needs_update": False}

    monkeypatch.setattr("app.tasmota.jobs.update_device_firmware", slow_updater)

    first = client.post("/api/update/all", json={"check_only": True})
    assert first.status_code == 202
    second = client.post("/api/update/all", json={"check_only": True})
    assert second.status_code == 409
    release.set()


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_jobs_endpoint_requires_auth():
    """Without a UI session or API key, the jobs endpoint is gated too."""
    jobs._reset_for_tests()
    app = create_app()
    app.config.update(TESTING=True, DEVICES_FILE="devices-dev.yaml")
    unauth = app.test_client()  # no GET / → no session
    assert unauth.get("/api/jobs/whatever").status_code == 401
