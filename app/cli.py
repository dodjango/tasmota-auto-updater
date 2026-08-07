"""Thin command-line wrapper over the maintained core in ``app/tasmota``.

Deliberately contains no update logic: the CLI resolves the device list and
orchestrates calls into ``app.tasmota``. Duplicating the update logic is what
killed the previous CLI (Phase 4 of the 2026-07 audit).
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping

EXIT_OK = 0
EXIT_OUTDATED = 1
EXIT_ERROR = 2

UNKNOWN_VERSION = "Unknown"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser: three verbs plus shared options."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Check, update or list configured Tasmota devices.",
    )
    parser.add_argument("-f", "--file", help="Path to the devices YAML file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for messages on stderr (default: WARNING).",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Compare every device against the latest release.")
    sub.add_parser("list", help="List configured devices and their firmware (no release lookup).")

    update = sub.add_parser("update", help="Update every outdated device.")
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
