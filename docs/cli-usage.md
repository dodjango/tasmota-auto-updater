# Command-Line Usage Guide

There is a thin CLI over the maintained core in `app/tasmota`: `python -m
app.cli`. It contains **no update logic of its own** — it resolves the device
list and calls into the same code the web UI and the REST API use.

The old `tasmota_updater.py` script is gone. Its options
(`--update-all`, `--check-only`, `--dry-run`, `--example` and the interactive
configuration wizard) do **not** carry over — running `tasmota_updater.py` now
only prints a pointer to this CLI and exits 1.

The documented invocation is always `python -m app.cli`, not a standalone
command, because the project is not installed as a package anywhere (not
locally, not in the container image). A `[project.scripts]` entry
(`tasmota-updater`) exists in `pyproject.toml`, but it only works after `pip
install .`, which nothing in this repo does — don't rely on it.

## Basic Usage

```bash
python -m app.cli check
python -m app.cli update
python -m app.cli list
```

In a container, without a new build layer:

```bash
podman run --rm -v ./devices.yaml:/app/devices.yaml:ro \
  --entrypoint python dodjango/tasmota-updater -m app.cli check
```

## The Three Verbs

| Verb | What it does | Talks to GitHub? |
|---|---|---|
| `check` | Compares every configured device against the latest Tasmota release. Reports, never flashes. | Yes |
| `update` | Classifies every device first, then flashes the outdated ones. | Yes |
| `list` | Lists configured devices and the firmware they report. No release lookup at all. | No |

`list` is immune to GitHub rate limits and can never report a device as
outdated — it doesn't compare anything. Use it as a plain inventory source.

## Options

Shared options go **after** the verb:

```
python -m app.cli {check|update|list} [-f PATH] [--json] [--log-level LEVEL]
python -m app.cli update [--timeout SECONDS]
```

`python -m app.cli list --json` works. `python -m app.cli --json list` does
not — the shared options belong to the subcommand parser, not the top-level
one.

| Option | Meaning |
|---|---|
| `-f`, `--file PATH` | Path to the devices YAML file. Resolved like the server: an explicit `-f` wins, otherwise `DEVICES_FILE` from the environment/`.env`, otherwise `devices.yaml`. |
| `--json` | Emit a JSON object on stdout instead of a table. |
| `--log-level LEVEL` | `DEBUG`, `INFO`, `WARNING` (default) or `ERROR`. Logs go to stderr, never stdout, so `--json` output stays parseable regardless of the level. |
| `--timeout SECONDS` | `update` only. Overrides the per-device total timeout. |

`update` only touches devices it classified as outdated. Re-flashing a
device that already reports the current version is not supported — the core
skips it and reports success without touching the device (see
`update_device_firmware()` in `app/tasmota/updater.py`), so a device that
misreports its own version cannot be recovered through the CLI today.

## Output

stdout carries only the result; stderr carries logs and errors.

### Human-readable (default)

One line per device plus a closing tally:

```
192.168.100.101  fake-tasmota-light1.local  12.0.2
192.168.100.102  fake-tasmota-switch1.local  11.1.0
192.168.100.103  fake-tasmota-plug1.local  12.0.2(tasmota-minimal)
192.168.100.104  fake-tasmota-slow-device.local  11.0.0
4 Geräte, 0 Fehler
```

(That example is `list` against the fake devices in `devices-dev.yaml` — the
German tally wording is user-visible output, not a translation gap.)

`check` against the same fixture, all four fake devices outdated:

```
192.168.100.101  fake-tasmota-light1.local  12.0.2 → 15.5.0     Update verfügbar
192.168.100.102  fake-tasmota-switch1.local  11.1.0 → 15.5.0     Update verfügbar
192.168.100.103  fake-tasmota-plug1.local  12.0.2(tasmota-minimal) → 15.5.0  Update verfügbar
192.168.100.104  fake-tasmota-slow-device.local  11.0.0 → 15.5.0     Update verfügbar
0 aktuell, 4 Update verfügbar, 0 Vergleich unbekannt, 0 Fehler
```

Note the third line: the version column (`12.0.2(tasmota-minimal) →
15.5.0`) is wider than its usual padding, and the label still starts two
spaces after it rather than gluing onto it — the columns are joined with a
fixed separator, not built from fixed-width padding alone, so an overrunning
column can never swallow the one after it. A device carries one of four
labels: `aktuell`, `Update verfügbar`, `Vergleich unbekannt`, or `nicht
erreichbar`.

### JSON (`--json`)

The core's own result dicts, unchanged, plus a computed summary and the exit
code. `json.dumps(..., sort_keys=True)` sorts keys alphabetically, and every
result carries all the fields the core returns, not just the ones relevant
to comparison — the excerpt below is a real, unedited run against two
devices (one fake, one with a bad IP, to show a real failure) and is not
representative of every field an update-vs-check run can carry:

```json
{
  "command": "check",
  "devices_file": "devices-doc-example.yaml",
  "exit_code": 2,
  "results": [
    {
      "current_version": "12.0.2",
      "dns_name": "fake-tasmota-light1.local",
      "ip": "192.168.100.101",
      "latest_version": "15.5.0",
      "message": "Update available",
      "needs_update": true,
      "success": true,
      "timeout_config": {
        "initial_wait": 10,
        "max_check_interval": 30.0,
        "min_check_interval": 2.0,
        "total_timeout": 240
      },
      "timeout_report": null,
      "update_completed": false,
      "update_started": false,
      "version_verification": null
    },
    {
      "current_version": "Unknown",
      "dns_name": "localhost",
      "ip": "127.0.0.1",
      "latest_version": "Unknown",
      "message": "Failed to get current firmware version",
      "needs_update": false,
      "success": false,
      "timeout_config": {
        "initial_wait": 10,
        "max_check_interval": 30.0,
        "min_check_interval": 2.0,
        "total_timeout": 240
      },
      "timeout_report": null,
      "update_completed": false,
      "update_started": false,
      "version_verification": null
    }
  ],
  "summary": {
    "comparison_unknown": 0,
    "failed": 1,
    "needs_update": 1,
    "total": 2,
    "up_to_date": 0
  }
}
```

`exit_code` is **2** here, not 1, because the unreachable device's failure
beats "outdated" — see Exit Codes below. `summary` is computed by the CLI
itself from `results`, not taken from the job runner's own tally — the
runner's summary has no way to express "comparison unknown" and does not
distinguish "up to date" from "not comparable". `list` results omit the
comparison fields (`latest_version`, `needs_update`); its summary has only
`total` and `failed`.

## Exit Codes

| | `check` | `update` | `list` |
|---|---|---|---|
| **0** | everything up to date | nothing to do, or all updates succeeded | every device reachable |
| **1** | at least one device outdated | — | — |
| **2** | error | at least one flash failed, or a device could not be reached or compared — including one `update` never touched | at least one device unreachable |

On mixed results the higher code wins: error (2) beats outdated (1) beats ok
(0). Exit code 1 only ever occurs for `check`.

For `update`, exit 2 does not necessarily mean a flash attempt failed:
`update` classifies every device first and only flashes the ones it selected
as outdated. A device it could not reach or could not compare is never
flashed at all, but it still counts toward `failed`/`comparison_unknown` and
still raises the exit code to 2. An operator debugging an exit-2 alert should
check *which* device carries the `nicht erreichbar` or `Vergleich unbekannt`
label before assuming a flash went wrong — it may be a device `update` never
touched.

**The rule that makes the exit codes trustworthy:** `needs_update: false` also
means "could not compare" — a failed release lookup reports
`latest_version: "Unknown"`. That case is never rendered as "up to date, exit
0"; it is an error (exit 2) and renders as `Vergleich unbekannt`. A cron job
that silently never alerts because of a rate-limited GitHub lookup would be
worse than one that never ran.

Other error conditions that produce exit 2: a missing or invalid devices
file, an empty device list, duplicate IPs in the devices file (rejected
before any device is touched), and an unreachable device.

## Automation Examples

The exit codes are the point — no `jq`, no output parsing needed for a simple
alert:

```bash
# Nightly check: alert only if something needs attention.
python -m app.cli check || mail -s "Tasmota veraltet" me@example.com
```

```bash
# Unattended weekly update, with a plain-text log for later inspection.
0 3 * * 0 cd /path/to/tasmota-updater && \
  python -m app.cli update --log-level INFO >> /var/log/tasmota-cli.log 2>&1
```

```bash
# Inventory for a monitoring script, no GitHub call and no rate-limit risk.
python -m app.cli list --json
```

## Interrupting a Run

`Ctrl-C` during `update` is caught: the CLI prints a warning to stderr and
exits 2. An OTA flash already started on a device keeps running there — it is
not, and cannot be, aborted from the CLI.

## Next Steps

- [Web Interface Guide](web-interface.md)
- [API Documentation](api.md)
- [Configuration Options](configuration.md)
- [Troubleshooting](troubleshooting.md)
