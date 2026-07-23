"""The CLI is deprecated (Phase 4): it must only print a notice and exit non-zero."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_prints_deprecation_and_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "tasmota_updater.py", "--check-only"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "deprecated" in result.stderr.lower()
    # It must not fall through into the old (broken) logic.
    assert "Traceback" not in result.stderr
