#!/usr/bin/env python3
"""Retired command-line interface for the Tasmota Remote Updater.

This entry point is gone: it duplicated the core update logic and had drifted
out of sync with it. A new, thin CLI over the maintained core lives at
``app/cli.py`` — invoke it as ``python -m app.cli``.

This stub remains only to give anyone still invoking the old entry point a clear
message and a pointer to the new one.
"""
import sys

_MESSAGE = """\
tasmota_updater.py — the old command-line interface — is gone. It duplicated the
update logic and had drifted out of sync with it.

There is a new, thin CLI over the maintained core:
  * python -m app.cli check      compare every device against the latest release
  * python -m app.cli update     update every outdated device
  * python -m app.cli list       list configured devices and their firmware

Other interfaces:
  * Web UI:   python server.py   ->  http://localhost:5001
  * REST API: POST /api/update, POST /api/update/all   (docs at /apidocs/)

The options of the old CLI (-f/--file aside) do not carry over: --update-all,
--check-only, --dry-run and --example are gone. See docs/cli-usage.md.
"""


def main() -> int:
    sys.stderr.write(_MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
