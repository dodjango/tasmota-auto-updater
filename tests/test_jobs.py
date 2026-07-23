"""Unit tests for the background batch-job runner (Phase 2)."""
import threading

import pytest

from app.tasmota import jobs


@pytest.fixture(autouse=True)
def _clean_jobs():
    jobs._reset_for_tests()
    yield
    jobs._reset_for_tests()


def _canned(results_by_ip):
    def _updater(config, check_only=False):
        return dict(results_by_ip[config["ip"]])
    return _updater


def test_batch_runs_and_summarises_synchronously():
    devices = [{"ip": "a"}, {"ip": "b"}]
    results = {
        "a": {"ip": "a", "success": True, "needs_update": True},
        "b": {"ip": "b", "success": True, "needs_update": False},
    }
    job_id = jobs.create_batch_job(
        devices, check_only=False, update_only_needed=False, global_timeout=None,
        updater=_canned(results), clock=lambda: 1.0, background=False,
    )
    job = jobs.get_job(job_id)
    assert job["status"] == "completed"
    assert job["total"] == 2
    assert job["completed"] == 2
    # update_only_needed=False → every device is "started"; both succeed → both updated
    assert job["summary"]["updated"] == 2
    assert len(job["results"]) == 2


def test_update_only_needed_filters_via_precheck():
    devices = [{"ip": "a"}, {"ip": "b"}]
    results = {
        "a": {"ip": "a", "success": True, "needs_update": True},
        "b": {"ip": "b", "success": True, "needs_update": False},
    }
    job_id = jobs.create_batch_job(
        devices, check_only=False, update_only_needed=True, global_timeout=None,
        updater=_canned(results), clock=lambda: 1.0, background=False,
    )
    job = jobs.get_job(job_id)
    assert job["status"] == "completed"
    assert job["total"] == 1          # only "a" needed an update
    assert job["summary"]["updated"] == 1


def test_runner_records_updater_exception():
    def boom(config, check_only=False):
        raise RuntimeError("device exploded")
    job_id = jobs.create_batch_job(
        [{"ip": "a"}], check_only=False, update_only_needed=False, global_timeout=None,
        updater=boom, clock=lambda: 1.0, background=False,
    )
    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert "device exploded" in job["error"]


def test_only_one_batch_at_a_time():
    started = threading.Event()
    release = threading.Event()

    def slow(config, check_only=False):
        started.set()
        release.wait(timeout=5)
        return {"ip": config["ip"], "success": True, "needs_update": False}

    first = jobs.create_batch_job([{"ip": "a"}], False, False, None, updater=slow, background=True)
    assert started.wait(timeout=5)
    second = jobs.create_batch_job([{"ip": "b"}], False, False, None, background=True)
    assert first is not None
    assert second is None  # guard rejects a concurrent batch
    release.set()


def test_unknown_job_is_none():
    assert jobs.get_job("nope") is None
