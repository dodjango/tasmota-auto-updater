"""Unit tests for the background batch-job runner (Phase 2)."""
import threading
import time

import pytest

from app.tasmota import discovery, jobs


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


def test_a_running_discovery_job_does_not_block_a_batch_update():
    """The deadlock this design had to sidestep.

    Both kinds share one store. If the batch exclusivity check keeps looking
    at every job in it, a scan blocks every update for as long as it runs —
    silently, and only in production where scans are slow.
    """
    def slow_scan(on_progress):
        time.sleep(0.2)
        return []

    discovery_id = jobs.create_discovery_job("scan", ["192.0.2.1"], runner=slow_scan)
    assert discovery_id is not None

    batch_id = jobs.create_batch_job(
        [{"ip": "192.0.2.9"}], check_only=True, update_only_needed=False,
        global_timeout=None, updater=lambda cfg, check_only=False: {"success": True},
        background=False,
    )
    assert batch_id is not None, "a running scan must not block a batch update"
    assert jobs.get_job(batch_id)["kind"] == "batch"
    assert jobs.get_job(discovery_id)["kind"] == "discovery"


def test_a_running_batch_update_does_not_block_discovery():
    """The same trap, from the other side."""
    started = threading.Event()
    release = threading.Event()

    def blocking_updater(config, check_only=False):
        started.set()
        release.wait(timeout=2)
        return {"success": True, "ip": config["ip"]}

    jobs.create_batch_job(
        [{"ip": "192.0.2.9"}], check_only=True, update_only_needed=False,
        global_timeout=None, updater=blocking_updater,
    )
    assert started.wait(timeout=2)

    discovery_id = jobs.create_discovery_job(
        "scan", ["192.0.2.1"], runner=lambda on_progress: [], background=False
    )
    release.set()
    assert discovery_id is not None, "a running batch update must not block a scan"


def test_only_one_discovery_job_runs_at_a_time():
    def slow_scan(on_progress):
        time.sleep(0.2)
        return []

    assert jobs.create_discovery_job("scan", ["192.0.2.1"], runner=slow_scan) is not None
    assert jobs.create_discovery_job("scan", ["192.0.2.2"], runner=slow_scan) is None


def test_discovery_job_records_results_and_progress():
    finding = {"ip": "192.0.2.5", "requires_auth": False}

    def runner(on_progress):
        on_progress(1, 1)
        return [finding]

    job_id = jobs.create_discovery_job("scan", ["192.0.2.5"], runner=runner, background=False)
    job = jobs.get_job(job_id)
    assert job["status"] == "completed"
    assert job["results"] == [finding]
    assert job["completed"] == 1 and job["total"] == 1


def test_an_empty_mdns_run_explains_why_rather_than_claiming_emptiness():
    job_id = jobs.create_discovery_job(
        "mdns", None, runner=lambda on_progress: [], background=False
    )
    job = jobs.get_job(job_id)
    assert job["status"] == "completed"
    assert job["results"] == []
    assert "bridge" in job["notice"]


def test_an_empty_scan_gets_no_mdns_notice():
    """The notice is about multicast, so it must not appear on a scan."""
    job_id = jobs.create_discovery_job(
        "scan", ["192.0.2.1"], runner=lambda on_progress: [], background=False
    )
    assert jobs.get_job(job_id)["notice"] is None


def test_mdns_job_without_zeroconf_ends_as_error():
    def runner(on_progress):
        raise discovery.MdnsUnavailable("no zeroconf here")

    job_id = jobs.create_discovery_job("mdns", None, runner=runner, background=False)
    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert "zeroconf" in job["error"]
