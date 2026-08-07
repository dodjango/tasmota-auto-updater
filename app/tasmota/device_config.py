"""Read, merge and atomically write the device configuration file.

`devices.yaml` is the source of truth. This module is the only place that
writes it. It deliberately holds no HTTP or update logic.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigWriteError(Exception):
    """The device configuration could not be written."""


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
