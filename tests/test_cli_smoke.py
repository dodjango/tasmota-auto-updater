"""End-to-end smoke test: run the CLI as a subprocess against fake devices."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    assert payload["summary"]["total"] >= 1
    assert payload["summary"]["failed"] == 0
    assert all("latest_version" not in entry for entry in payload["results"])


def test_check_json_is_parseable_whatever_the_release_lookup_does():
    result = _run("check", "--json")
    assert result.returncode in (0, 1, 2), result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "check"
    assert payload["exit_code"] == result.returncode
    assert set(payload["summary"]) == {
        "total",
        "up_to_date",
        "needs_update",
        "comparison_unknown",
        "failed",
    }


def test_human_output_ends_with_a_tally():
    result = _run("list")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1].endswith("Fehler")
