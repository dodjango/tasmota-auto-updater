"""Thin command-line wrapper over the maintained core in ``app/tasmota``.

Deliberately contains no update logic: the CLI resolves the device list and
orchestrates calls into ``app.tasmota``. Duplicating the update logic is what
killed the previous CLI (Phase 4 of the 2026-07 audit).
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.tasmota import jobs, updater, utils

EXIT_OK = 0
EXIT_OUTDATED = 1
EXIT_ERROR = 2

UNKNOWN_VERSION = "Unknown"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser: three verbs plus shared options."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-f", "--file", help="Path to the devices YAML file.")
    common.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    common.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for messages on stderr (default: WARNING).",
    )

    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Check, update or list configured Tasmota devices.",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "check",
        parents=[common],
        help="Compare every device against the latest release.",
    )
    sub.add_parser(
        "list",
        parents=[common],
        help="List configured devices and their firmware (no release lookup).",
    )

    update = sub.add_parser(
        "update",
        parents=[common],
        help="Update every outdated device.",
    )
    update.add_argument(
        "--timeout",
        type=int,
        help="Override the per-device total timeout in seconds.",
    )
    update.add_argument(
        "--force",
        action="store_true",
        help="Flash every configured device, including up-to-date ones.",
    )
    return parser


def resolve_devices_file(explicit: str | None, env: Mapping[str, str]) -> str:
    """Resolve the devices file the same way ``server.py`` does."""
    if explicit:
        return explicit
    return env.get("DEVICES_FILE", "devices.yaml")


def classify(result: Mapping[str, Any]) -> str:
    """Classify one core result dict. The four classes are mutually exclusive.

    ``needs_update: False`` also means "could not compare" when the release
    lookup failed, so an unknown ``latest_version`` must be recognised before
    anything is called up to date (#91).
    """
    if not result.get("success"):
        return "failed"
    latest = result.get("latest_version")
    if not latest or latest == UNKNOWN_VERSION:
        return "comparison_unknown"
    if result.get("needs_update"):
        return "needs_update"
    return "up_to_date"


def summarize(results: Sequence[Mapping[str, Any]], command: str
              ) -> dict[str, int]:
    """Build the tally for ``command``. Shapes differ per command by design."""
    classes = [classify(result) for result in results]
    total = len(results)
    failed = classes.count("failed")
    unknown = classes.count("comparison_unknown")

    if command == "list":
        return {"total": total, "failed": failed}

    if command == "update":
        updated = sum(1 for result in results if result.get("update_completed"))
        # A device that was updated successfully now reports the new version and
        # would classify as up_to_date — it must not be counted as skipped too.
        skipped = sum(
            1
            for result, cls in zip(results, classes, strict=True)
            if cls == "up_to_date" and not result.get("update_completed")
        )
        return {
            "total": total,
            "updated": updated,
            "skipped": skipped,
            "comparison_unknown": unknown,
            "failed": failed,
        }

    return {
        "total": total,
        "up_to_date": classes.count("up_to_date"),
        "needs_update": classes.count("needs_update"),
        "comparison_unknown": unknown,
        "failed": failed,
    }


def exit_code_for(command: str, summary: Mapping[str, int]) -> int:
    """Map a tally to an exit code. Error beats outdated beats ok."""
    if summary.get("failed") or summary.get("comparison_unknown"):
        return EXIT_ERROR
    if command == "check" and summary.get("needs_update"):
        return EXIT_OUTDATED
    return EXIT_OK


_CHECK_LABELS = {
    "failed": "nicht erreichbar",
    "comparison_unknown": "Vergleich unbekannt",
    "needs_update": "Update verfügbar",
    "up_to_date": "aktuell",
}


def _list_label(result: Mapping[str, Any]) -> str:
    """`list` performs no release lookup, so no comparison wording applies."""
    return "" if result.get("success") else "nicht erreichbar"


def _update_label(result: Mapping[str, Any]) -> str:
    """Label for an update run. A just-updated device still carries
    ``needs_update`` from its pre-update comparison, so the class alone lies."""
    if result.get("update_completed"):
        return "aktualisiert"
    if not result.get("success"):
        return "Update fehlgeschlagen" if result.get("update_started") else "nicht erreichbar"
    if classify(result) == "comparison_unknown":
        return "Vergleich unbekannt"
    return "übersprungen (aktuell)"


def _version_column(result: Mapping[str, Any]) -> str:
    """Format the version column: current, current→latest, or —."""
    current = result.get("current_version") or "—"
    if not result.get("success"):
        return "—"
    if classify(result) == "needs_update":
        return f"{current} → {result.get('latest_version')}"
    return str(current)


def _tally_line(command: str, summary: Mapping[str, int]) -> str:
    """Format the summary line, tailored to the command."""
    if command == "list":
        return f"{summary.get('total', 0)} Geräte, {summary.get('failed', 0)} Fehler"
    if command == "update":
        return (
            f"{summary.get('updated', 0)} aktualisiert, "
            f"{summary.get('skipped', 0)} übersprungen, "
            f"{summary.get('comparison_unknown', 0)} Vergleich unbekannt, "
            f"{summary.get('failed', 0)} Fehler"
        )
    return (
        f"{summary.get('up_to_date', 0)} aktuell, "
        f"{summary.get('needs_update', 0)} Update verfügbar, "
        f"{summary.get('comparison_unknown', 0)} Vergleich unbekannt, "
        f"{summary.get('failed', 0)} Fehler"
    )


def render_human(
    command: str,
    results: Sequence[Mapping[str, Any]],
    summary: Mapping[str, int],
) -> str:
    """One line per device plus a closing tally, sized for a cron mail."""
    lines = []
    for result in results:
        if command == "update":
            label = _update_label(result)
        elif command == "list":
            label = _list_label(result)
        else:
            label = _CHECK_LABELS[classify(result)]
        name = str(result.get("dns_name") or "")
        line = (
            f"{str(result.get('ip', '?')):<16}{name:<16}{_version_column(result):<20}{label}"
        )
        lines.append(line.rstrip())
    lines.append(_tally_line(command, summary))
    return "\n".join(lines)


def render_json(
    command: str,
    devices_file: str,
    results: Sequence[Mapping[str, Any]],
    summary: Mapping[str, int],
    exit_code: int,
) -> str:
    """Emit the core result dicts unchanged, plus tally and exit code."""
    payload = {
        "command": command,
        "devices_file": devices_file,
        "results": [dict(result) for result in results],
        "summary": dict(summary),
        "exit_code": exit_code,
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


class CliError(Exception):
    """A condition that must end the run with EXIT_ERROR."""


def run_batch(
    devices: Sequence[Mapping[str, Any]],
    *,
    check_only: bool,
    timeout: int | None,
) -> list[dict[str, Any]]:
    """Run the shared batch runner synchronously and return its results.

    ``update_only_needed`` is always False: the CLI decides itself which
    devices to touch, because the runner's internal filter drops skipped
    devices from the results and would hide a failed comparison.
    """
    job_id = jobs.create_batch_job(
        [dict(device) for device in devices],
        check_only=check_only,
        update_only_needed=False,
        global_timeout=timeout,
        background=False,
    )
    if job_id is None:
        raise CliError("Could not create a batch job — another one is already running.")
    job = jobs.get_job(job_id)
    if job is None:
        raise CliError(f"Batch job {job_id} disappeared before it could be read.")
    if job.get("status") == "error":
        raise CliError(str(job.get("error") or "The batch runner failed."))
    return [dict(result) for result in job.get("results", [])]


def cmd_check(devices: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compare every configured device against the latest release."""
    return run_batch(devices, check_only=True, timeout=None)


def cmd_update(
    devices: Sequence[Mapping[str, Any]],
    *,
    force: bool,
    timeout: int | None,
) -> list[dict[str, Any]]:
    """Update outdated devices in two passes: classify, then flash the subset.

    The runner's own ``update_only_needed`` filter is not used: it drops
    skipped devices from the results, which would make a failed release lookup
    indistinguishable from "everything current".
    """
    checked = run_batch(devices, check_only=True, timeout=None)
    # With --force, up-to-date devices are flashed too — but never a device we
    # could not classify: flashing blind is worse than doing nothing.
    wanted = ("needs_update", "up_to_date") if force else ("needs_update",)
    selected_ips = [result["ip"] for result in checked if classify(result) in wanted]
    if not selected_ips:
        return checked

    by_ip = {device.get("ip"): device for device in devices}
    subset = [by_ip[ip] for ip in selected_ips if ip in by_ip]
    updated = {
        result.get("ip"): result
        for result in run_batch(subset, check_only=False, timeout=timeout)
    }
    # Every selected device must come back with a pass-two result. Silently
    # falling back to its pass-one entry would leave it carrying a stale
    # needs_update flag while landing in none of the tally's buckets — the
    # totals stop adding up and a device that needed flashing looks untouched.
    missing = [ip for ip in selected_ips if ip not in updated]
    if missing:
        raise CliError(
            "The update pass returned no result for: " + ", ".join(str(ip) for ip in missing)
        )
    return [updated.get(result["ip"], result) for result in checked]


def cmd_list(devices: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Inventory: what is configured and what firmware runs on it.

    Deliberately LAN-only — no release lookup, so no GitHub rate limit can
    break it, and it can never report "outdated".
    """
    results: list[dict[str, Any]] = []
    for device in devices:
        info = updater.get_device_firmware_version(dict(device))
        version = info.get("version") if isinstance(info, dict) else None
        result: dict[str, Any] = {
            "ip": device.get("ip"),
            "success": bool(version),
            "current_version": version or UNKNOWN_VERSION,
        }
        if device.get("dns_name"):
            result["dns_name"] = device["dns_name"]
        results.append(result)
    return results
