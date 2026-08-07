"""Thin command-line wrapper over the maintained core in ``app/tasmota``.

Deliberately contains no update logic: the CLI resolves the device list and
orchestrates calls into ``app.tasmota``. Duplicating the update logic is what
killed the previous CLI (Phase 4 of the 2026-07 audit).
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from typing import Any

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
