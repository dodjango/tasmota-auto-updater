"""Read, merge and atomically write the device configuration file.

`devices.yaml` is the source of truth. This module is the only place that
writes it. It deliberately holds no HTTP or update logic.
"""
from __future__ import annotations

import copy
import os
import shutil
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml


class ConfigWriteError(Exception):
    """The device configuration could not be written."""


class ConfigReadError(Exception):
    """The device configuration exists but could not be understood."""


MANAGED_FIELDS: tuple[str, ...] = ("ip", "username", "password", "dns_name", "timeout")


def read_document(target: Path) -> dict[str, Any]:
    """Read the full YAML mapping, for preserving keys this module does not manage.

    Nothing writes such a key today, but the per-device merge already goes to
    lengths to preserve unknown fields (``fake``, ``firmware_info``, ...) and
    the document level should match: a save must not drop a top-level key it
    was never asked to touch.

    Same failure semantics as ``read_devices()``: a missing file is an empty
    mapping, never a reason to raise. Invalid YAML or a document that is not
    a mapping with a ``devices`` list does raise — the merge baseline must
    not be silently empty.
    """
    if not target.exists():
        return {}
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigReadError(f"{target} is not valid YAML: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("devices", []), list):
        raise ConfigReadError(f"{target} does not contain a 'devices' list")
    return raw


def read_devices(target: Path) -> list[dict[str, Any]]:
    """Read the configuration for the write path.

    Unlike ``utils.load_devices_from_file()``, which answers every failure
    with an empty list, this raises. An empty answer here means the file
    really is empty — never that it could not be parsed. The merge baseline
    must not be silently empty: that would drop every stored password and
    fake-device fixture on the next write.
    """
    return list(read_document(target).get("devices") or [])


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


def write_devices(
    target: Path,
    devices: list[dict[str, Any]],
    document: dict[str, Any] | None = None,
) -> None:
    """Replace the device file atomically, keeping one backup generation.

    ``document`` is the previously-read full mapping (see ``read_document()``);
    any key besides ``devices`` in it is carried over unchanged. Omit it to
    write a file containing only ``devices`` — what every caller before this
    parameter existed did.
    """
    if not is_writable(target):
        raise ConfigWriteError(
            f"{target} is not writable. If the file is bind-mounted individually, "
            "mount its directory instead."
        )

    body = dict(document) if document else {}
    body["devices"] = devices
    payload = yaml.safe_dump(body, sort_keys=False, allow_unicode=True)

    fd, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".devices-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            # mkstemp() creates the file 0600, and Path.replace() carries that
            # onto the target — silently tightening devices.yaml's permissions
            # on the first UI save and locking out the SSH editing path the
            # design promises stays open. Match the target's mode first.
            temp_path.chmod(stat.S_IMODE(target.stat().st_mode))
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
        temp_path.replace(target)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise ConfigWriteError(f"Could not write {target}: {exc}") from exc


_replace_lock = threading.Lock()


def replace_devices(target: Path, submitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read, merge and write in one atomic unit, for concurrent callers.

    ``read → merge → write`` is not atomic across requests. With two
    overlapping writes — two browser tabs, a fast double-click, the gthread
    worker makes both reachable — the second writer's ``.bak`` would be the
    *first* writer's output, not the original pre-edit state, so that state is
    gone from both the file and the backup. Holding this lock across the whole
    sequence serialises overlapping saves so each one's backup is a real,
    previously-live version of the file.
    """
    with _replace_lock:
        document = read_document(target)
        existing = list(document.get("devices") or [])
        merged = merge_devices(existing, submitted)
        write_devices(target, merged, document=document)
        return merged
