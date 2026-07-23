#!/usr/bin/env python3
"""Deprecated command-line interface for the Tasmota Remote Updater.

The CLI is deprecated and no longer maintained. It duplicated the core update
logic (and had drifted out of sync with it). Use the web interface or the REST
API instead, which share the maintained core in ``app/tasmota``.

This stub remains only to give anyone still invoking the old entry point a clear
message and a pointer to the supported interfaces.
"""
import sys

_MESSAGE = """\
tasmota_updater.py — the command-line interface — is deprecated and no longer
maintained.

Use one of the supported interfaces instead:
  * Web UI:    python server.py        ->  http://localhost:5001
  * Container: see README.md / compose.example.yml
  * REST API:  POST /api/update  and  POST /api/update/all   (docs at /apidocs/)

See docs/cli-usage.md for details and migration notes.
"""


def main() -> int:
    sys.stderr.write(_MESSAGE)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
