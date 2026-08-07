"""End-to-end smoke test: run the CLI as a subprocess against fake devices."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEVICES_FILE = REPO_ROOT / "devices-dev.yaml"

# Matches the shape updater.save_to_cache()/get_cached_data() use for the
# 'latest_release' cache — see app/tasmota/updater.py. Pre-seeding it makes
# `check` deterministic without touching production code: no live,
# unauthenticated GitHub call inside the required pytest job (see #76 —
# exactly this kind of live dependency is what makes CI flaky).
CACHE_FILE = REPO_ROOT / "app" / "tasmota" / "cache" / "latest_release.json"
STUBBED_LATEST_VERSION = "99.0.0"  # newer than every fake device in devices-dev.yaml
STUBBED_RELEASE = {
    "version": STUBBED_LATEST_VERSION,
    "release_date": "2026-01-01T00:00:00Z",
    "release_notes": "stubbed for test_cli_smoke",
    "download_url": "https://example.invalid/tasmota.bin",
    "release_url": "https://github.com/arendst/Tasmota/releases/",
}


@pytest.fixture
def stubbed_release_cache():
    """Pre-seed the release cache so `check` never calls GitHub.

    Backs up and restores whatever cache file the developer already has, so
    running this test does not leave their own cache modified.
    """
    original = CACHE_FILE.read_bytes() if CACHE_FILE.exists() else None
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"cache_timestamp": datetime.now().isoformat(), "data": STUBBED_RELEASE})
    )
    try:
        yield
    finally:
        if original is None:
            CACHE_FILE.unlink(missing_ok=True)
        else:
            CACHE_FILE.write_bytes(original)


def _configured_device_count() -> int:
    with DEVICES_FILE.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return len(config["devices"])


def _run(command, *args):
    return subprocess.run(
        [sys.executable, "-m", "app.cli", command, "-f", "devices-dev.yaml", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_list_json_reports_every_fake_device():
    result = _run("list", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "list"
    # A dropped device must not slip past a loose ">= 1" — every configured
    # device must show up (finding 4: a silently shrunk devices-dev.yaml
    # would still pass a ">= 1" check).
    assert payload["summary"]["total"] == _configured_device_count()
    assert payload["summary"]["failed"] == 0
    assert all("latest_version" not in entry for entry in payload["results"])


def test_check_json_is_parseable_with_a_stubbed_release_lookup(stubbed_release_cache):
    result = _run("check", "--json")
    payload = json.loads(result.stdout)
    device_count = _configured_device_count()
    # Every fake device in devices-dev.yaml is older than STUBBED_LATEST_VERSION,
    # so the outcome — and therefore the exit code — is now deterministic.
    assert result.returncode == 1, result.stderr
    assert payload["command"] == "check"
    assert payload["exit_code"] == 1
    assert payload["summary"] == {
        "total": device_count,
        "up_to_date": 0,
        "needs_update": device_count,
        "comparison_unknown": 0,
        "failed": 0,
    }
    assert all(r["latest_version"] == STUBBED_LATEST_VERSION for r in payload["results"])


def test_human_output_ends_with_a_tally():
    result = _run("list")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1].endswith("Fehler")
