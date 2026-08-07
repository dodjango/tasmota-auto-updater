"""Read, merge and atomically write the device configuration file.

`devices.yaml` is the source of truth. This module is the only place that
writes it. It deliberately holds no HTTP or update logic.
"""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml


class ConfigWriteError(Exception):
    """The device configuration could not be written."""


MANAGED_FIELDS: tuple[str, ...] = ("ip", "username", "password", "dns_name", "timeout")


def merge_devices(
    existing: list[dict[str, Any]],
    submitted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge the editor's view over the configuration on disk.

    The submitted list decides membership and order; a device missing from it is
    deleted. Everything this module does not manage — ``fake``,
    ``firmware_info``, fields a later version introduces — is carried over from
    the existing entry, matched by IP. A password is only replaced when one is
    submitted, and only removed on explicit request. An entry without an ``ip``
    is skipped on both sides — it cannot be matched and must not be written. If
    the file on disk has duplicate IPs, the last one wins; earlier duplicates
    are dropped.
    """
    by_ip = {device["ip"]: device for device in existing if device.get("ip")}
    merged: list[dict[str, Any]] = []

    for entry in submitted:
        if not entry.get("ip"):
            continue

        current = copy.deepcopy(by_ip.get(entry["ip"], {}))
        remove_password = bool(entry.get("remove_password"))

        for field in MANAGED_FIELDS:
            if field == "password":
                continue
            if entry.get(field) not in (None, ""):
                current[field] = entry[field]
            else:
                current.pop(field, None)

        if entry.get("password"):
            current["password"] = entry["password"]
        elif remove_password:
            current.pop("password", None)

        current.pop("remove_password", None)
        merged.append(current)

    return merged


def is_writable(target: Path) -> bool:
    """Can we replace ``target`` atomically?

    Checking the directory alone is not enough. With a single-file bind mount
    the directory is writable while the file itself is a mount point, and
    ``os.replace()`` onto a mount point fails with EBUSY — at save time, long
    after the UI told the user everything was fine.
    """
    if not os.access(target.parent, os.W_OK):
        return False
    try:
        return not target.is_mount()
    except OSError:  # pragma: no cover - unreadable path, treat as not writable
        return False


def write_devices(target: Path, devices: list[dict[str, Any]]) -> None:
    """Replace the device file atomically, keeping one backup generation."""
    if not is_writable(target):
        raise ConfigWriteError(
            f"{target} is not writable. If the file is bind-mounted individually, "
            "mount its directory instead."
        )

    payload = yaml.safe_dump({"devices": devices}, sort_keys=False, allow_unicode=True)

    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".devices-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        os.replace(temp_path, target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise ConfigWriteError(f"Could not write {target}: {exc}") from exc
