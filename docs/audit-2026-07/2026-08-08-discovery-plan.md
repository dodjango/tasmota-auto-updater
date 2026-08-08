# Network Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find Tasmota devices on the LAN — by mDNS or by a fenced IP range scan — and let the user adopt the findings into the device editor.

**Architecture:** A new core module `app/tasmota/discovery.py` holds pure search logic with no Flask and no job handling, mirroring `updater.py`. The existing in-memory job store gains a `kind` field so a discovery job and a batch update no longer block each other. The API layer owns the scan policy; the core owns the mechanics. Discovery has no write path at all — findings become unsaved rows in the editor and the user saves them through the existing `PUT /api/config/devices`.

**Tech Stack:** Python 3.10+, Flask-RESTful, Marshmallow, `requests`, `zeroconf`, Alpine.js v3, Bulma, pytest, pytest-playwright.

Design spec: `docs/audit-2026-07/2026-08-08-discovery-design.md`.

## Global Constraints

- **Dependency floor: `zeroconf>=0.149.12`.** Anything older carries GHSA-9663-mqmp-p9mm / CVE-2026-48045, a LAN-local memory exhaustion through flooded TC-bit mDNS queries — precisely this feature's threat model. The floor is not cosmetic.
- **Never send credentials while probing.** Not from `devices.yaml`, not from anywhere. `requires_auth` is a result, never a reason for a second attempt.
- **Scan concurrency is fixed at 64, host timeout at 1.5 s, no retries.** Neither is reachable from the API — a per-request concurrency knob is a DoS button behind the session.
- **`allow_redirects=False` and a 64 KiB response cap on every probe.**
- **Scan policy lives in the API layer** (`validate_scan_target()`), never inside `discovery.py`. The core scanner must stay testable against a loopback stub, and the policy forbids loopback.
- **The web UI is English** (`<html lang="en">`), including every new string. Log messages and code comments follow the surrounding code.
- **Every interactive element gets a tooltip starting with an action verb**; the scan button's tooltip states outright that it sends an HTTP request to every address in the range.
- **Prefer `data-testid` over class selectors** in new markup — a second `.notification.is-danger` has already broken the e2e suite through Playwright strict mode.
- Test command for the green core: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`. Running a single file needs `-o addopts=""` or the coverage flags fail the partial run.
- `create_app()` takes **no** arguments — construct it, then `config.update({...})`. An authenticated test client needs `session["ui_authenticated"] = True`.

## File Structure

| File | Responsibility |
|---|---|
| `app/tasmota/discovery.py` (create) | Pure search: probe, parse, scan pool, mDNS browse. No Flask, no jobs, no policy. |
| `app/tasmota/jobs.py` (modify) | Gains `kind`, kind-scoped exclusivity, `create_discovery_job()`. |
| `app/tasmota/api.py` (modify) | `validate_scan_target()`, `DiscoveryResource`, route registration, Swagger docs. |
| `app/static/js/discovery.js` (create) | Alpine component: modal state, polling, selection. |
| `app/static/js/devices-editor.js` (modify) | Accepts adopted findings as unsaved rows. |
| `app/templates/index.html` (modify) | Discovery button and modal markup. |
| `tests/test_discovery.py` (create) | Unit tests for parse/validate + the ungmocked loopback scan. |
| `tests/test_discovery_api.py` (create) | Endpoint contract: 202/400/409/401. |
| `tests/test_jobs.py` (modify) | Regression: discovery and batch jobs do not block each other. |
| `tests/e2e/test_discovery.py` (create) | Modal, stubbed job, adoption into the editor. |
| `requirements.txt` (modify) | `zeroconf>=0.149.12`. |
| `docs/*` (modify) | container-setup, api, web-interface, configuration, contributing. |

---

### Task 1: Core probe and parse

**Files:**
- Create: `app/tasmota/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_status(payload: dict, ip: str) -> dict | None`, `probe_host(ip: str, *, timeout: float = 1.5, port: int = 80) -> dict | None`. The returned dict has keys `ip`, `hostname`, `friendly_name`, `module`, `firmware_version`, `mac`, `requires_auth`.

Note the `port` keyword on `probe_host` — it exists so Task 2's ungmocked test can point the real scanner at a loopback stub on an ephemeral port. Production callers never pass it.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the discovery core."""
import pytest

from app.tasmota import discovery

TASMOTA_STATUS = {
    "Status": {"Module": 1, "DeviceName": "Hallway", "FriendlyName": ["Hallway Light"]},
    "StatusFWR": {"Version": "14.2.0(release-tasmota)", "Hardware": "ESP8266EX"},
    "StatusNET": {"Hostname": "tasmota-1234", "IPAddress": "192.168.1.42",
                  "Mac": "AA:BB:CC:DD:EE:FF"},
}


def test_parse_status_extracts_the_fields_the_ui_shows():
    result = discovery.parse_status(TASMOTA_STATUS, "192.168.1.42")
    assert result == {
        "ip": "192.168.1.42",
        "hostname": "tasmota-1234",
        "friendly_name": "Hallway Light",
        "module": "ESP8266EX",
        "firmware_version": "14.2.0(release-tasmota)",
        "mac": "AA:BB:CC:DD:EE:FF",
        "requires_auth": False,
    }


def test_parse_status_survives_a_sparse_payload():
    """A minimal device still answers Status 0 — it must not crash the scan."""
    result = discovery.parse_status({"Status": {}}, "192.168.1.7")
    assert result is not None
    assert result["ip"] == "192.168.1.7"
    assert result["firmware_version"] is None
    assert result["friendly_name"] is None


def test_parse_status_rejects_a_foreign_json_device():
    """A printer answering JSON is not a Tasmota. No Status block, no entry."""
    assert discovery.parse_status({"printer": {"model": "X"}}, "192.168.1.9") is None


def test_parse_status_rejects_a_non_mapping():
    assert discovery.parse_status([1, 2, 3], "192.168.1.9") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_discovery.py -o addopts="" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tasmota.discovery'`

- [ ] **Step 3: Write the module**

```python
"""Find Tasmota devices on the local network.

Pure search logic: probe a host, understand its answer, run a bounded pool of
probes, browse mDNS. No Flask, no job handling, and deliberately no policy —
``scan_network()`` takes a finished host list, never a CIDR. Deciding *what may
be scanned* belongs to the API layer (``api.validate_scan_target()``); keeping
it out of here is what lets the scanner be tested against a loopback stub,
which that policy forbids.

Nothing in this module ever sends credentials. A device behind a web password
is reported as ``requires_auth`` and left alone.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# A Tasmota `Status 0` answer is a few KiB. The cap is not about Tasmota — it
# stops a hostile host on the LAN from holding a worker on an endless stream.
MAX_RESPONSE_BYTES = 64 * 1024

# Tasmota's answer when a web password is set. It arrives with HTTP 401.
AUTH_MARKER = "need user&password"


def parse_status(payload: Any, ip: str) -> Optional[dict[str, Any]]:
    """Turn a ``Status 0`` answer into a finding, or None if it is not Tasmota.

    Strict on purpose: without the ``Status`` block, every JSON-speaking
    printer and camera on the network would land in the suggestion list.
    Everything below that block is optional — a minimal firmware answers with
    far less, and that is still a device worth showing.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("Status"), dict):
        return None

    status = payload.get("Status") or {}
    firmware = payload.get("StatusFWR") or {}
    network = payload.get("StatusNET") or {}

    friendly = status.get("FriendlyName")
    if isinstance(friendly, list):
        friendly = friendly[0] if friendly else None

    return {
        "ip": network.get("IPAddress") or ip,
        "hostname": network.get("Hostname"),
        "friendly_name": friendly or status.get("DeviceName"),
        "module": firmware.get("Hardware"),
        "firmware_version": firmware.get("Version"),
        "mac": network.get("Mac"),
        "requires_auth": False,
    }


def probe_host(ip: str, *, timeout: float = 1.5, port: int = 80) -> Optional[dict[str, Any]]:
    """Ask one host whether it is a Tasmota device.

    Never sends credentials, never follows a redirect, never retries. ``port``
    exists so the scanner can be tested against a local stub; production
    callers leave it at 80.
    """
    url = f"http://{ip}:{port}/cm"
    try:
        response = requests.get(
            url,
            params={"cmnd": "Status 0"},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
    except requests.exceptions.RequestException:
        # The overwhelming majority of addresses in a range answer nothing at
        # all. That is the normal case, not an error worth logging per host.
        return None

    try:
        body = response.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True) or b""
    except Exception:  # pragma: no cover - defensive: broken stream mid-read
        return None
    finally:
        response.close()

    if len(body) > MAX_RESPONSE_BYTES:
        logger.debug("%s: response exceeded %d bytes, ignored", ip, MAX_RESPONSE_BYTES)
        return None

    text = body.decode("utf-8", errors="replace")

    if response.status_code == 401:
        if AUTH_MARKER in text.lower():
            return {
                "ip": ip, "hostname": None, "friendly_name": None, "module": None,
                "firmware_version": None, "mac": None, "requires_auth": True,
            }
        return None

    if response.status_code != 200:
        return None

    try:
        payload = requests.models.complexjson.loads(text)
    except ValueError:
        return None

    return parse_status(payload, ip)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_discovery.py -o addopts="" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/discovery.py tests/test_discovery.py
git commit -F- <<'MSG'
feat(discovery): probe a host and understand its Status 0 answer

Strict identification on purpose: without a `Status` block the answer is
discarded, so JSON-speaking printers and cameras stay out of the suggestion
list. A 401 carrying Tasmota's `Need user&password` marker counts as a find
and is reported as requires_auth — as a result, never as a reason to try
again with credentials.

The response body is capped at 64 KiB and redirects are not followed, so a
hostile host on the LAN can neither hold a worker on an endless stream nor
steer the probe somewhere else.
MSG
```

---

### Task 2: The scan pool, tested against a real server

**Files:**
- Modify: `app/tasmota/discovery.py`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `probe_host()` from Task 1.
- Produces: `scan_network(hosts: list[str], *, probe=probe_host, workers: int = 64, on_progress=None) -> list[dict]`. `on_progress` is called as `on_progress(completed: int, total: int)` after each host.

This task carries the plan's most important test. Every `--force` test in [#126](https://github.com/dodjango/tasmota-auto-updater/issues/126) mocked the runner and thereby hid that the core could not do what the surface promised. A scan test that mocks `probe_host` proves only that a thread pool calls a function. So one test drives the real `probe_host` against three real HTTP servers on loopback.

- [ ] **Step 1: Write the failing tests**

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _StubHandler(BaseHTTPRequestHandler):
    """Answers like the device its `mode` says. Set by the factory below."""

    mode = "tasmota"

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's interface
        if self.mode == "tasmota":
            body = json.dumps(TASMOTA_STATUS).encode()
            self.send_response(200)
        elif self.mode == "auth":
            body = json.dumps({"WARNING": "Need user&password"}).encode()
            self.send_response(401)
        else:
            body = json.dumps({"printer": {"model": "X"}}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output readable
        pass


def _start_stub(mode):
    handler = type("Handler", (_StubHandler,), {"mode": mode})
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def stub_servers():
    servers = {mode: _start_stub(mode) for mode in ("tasmota", "auth", "foreign")}
    yield {mode: s.server_address[1] for mode, s in servers.items()}
    for server in servers.values():
        server.shutdown()


def test_scan_finds_real_devices_without_mocking_the_probe(stub_servers):
    """The one test that drives the real probe over a real socket.

    Mocking probe_host here would only prove that a thread pool calls a
    function — exactly the blind spot that let #126 ship.
    """
    found = []
    for mode, port in stub_servers.items():
        results = discovery.scan_network(
            ["127.0.0.1"],
            probe=lambda ip, port=port: discovery.probe_host(ip, port=port, timeout=2.0),
        )
        found.extend(results)

    by_auth = {entry["requires_auth"]: entry for entry in found}
    assert len(found) == 2, "the foreign JSON device must not be reported"
    assert by_auth[False]["firmware_version"] == "14.2.0(release-tasmota)"
    assert by_auth[True]["ip"] == "127.0.0.1"


def test_scan_reports_progress_for_every_host():
    seen = []
    discovery.scan_network(
        [f"192.0.2.{n}" for n in range(1, 6)],
        probe=lambda ip: None,
        on_progress=lambda completed, total: seen.append((completed, total)),
    )
    assert [c for c, _ in seen] == [1, 2, 3, 4, 5]
    assert {t for _, t in seen} == {5}


def test_scan_survives_a_probe_that_raises():
    """One broken host must not abort the whole range."""
    def flaky(ip):
        if ip.endswith(".2"):
            raise RuntimeError("boom")
        return {"ip": ip, "requires_auth": False}

    results = discovery.scan_network(["192.0.2.1", "192.0.2.2", "192.0.2.3"], probe=flaky)
    assert sorted(r["ip"] for r in results) == ["192.0.2.1", "192.0.2.3"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_discovery.py -o addopts="" -v`
Expected: FAIL — `AttributeError: module 'app.tasmota.discovery' has no attribute 'scan_network'`

- [ ] **Step 3: Implement the pool**

Append to `app/tasmota/discovery.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable

# Fixed, and deliberately not reachable from the API. A per-request concurrency
# knob behind a session is a denial-of-service button.
DEFAULT_WORKERS = 64


def scan_network(
    hosts: list[str],
    *,
    probe: Callable[[str], Optional[dict[str, Any]]] = probe_host,
    workers: int = DEFAULT_WORKERS,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> list[dict[str, Any]]:
    """Probe every host in ``hosts`` concurrently and return the finds.

    Takes a finished host list, never a CIDR: what may be scanned is a policy
    question and belongs to the caller. A probe that raises costs its own host
    and nothing else — in a range of a thousand addresses, one broken host must
    not abort the sweep.
    """
    total = len(hosts)
    results: list[dict[str, Any]] = []
    completed = 0

    if not hosts:
        return results

    with ThreadPoolExecutor(max_workers=min(workers, total)) as pool:
        futures = {pool.submit(probe, host): host for host in hosts}
        for future in as_completed(futures):
            completed += 1
            try:
                found = future.result()
            except Exception as exc:  # one bad host, not a failed scan
                logger.debug("%s: probe failed: %s", futures[future], exc)
                found = None
            if found:
                results.append(found)
            if on_progress:
                on_progress(completed, total)

    return results


def hosts_in_network(network: Any) -> list[str]:
    """Every usable address in an ``ipaddress`` network, as strings.

    ``.hosts()`` already leaves out the network and broadcast address for a
    normal IPv4 network — the point of going through it rather than iterating
    the network itself.
    """
    return [str(host) for host in network.hosts()]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_discovery.py -o addopts="" -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/tasmota/discovery.py tests/test_discovery.py
git commit -F- <<'MSG'
feat(discovery): scan a host list with a bounded worker pool

Concurrency is fixed at 64 and cannot be reached from the API — a
per-request concurrency knob behind a session would be a DoS button. A probe
that raises costs its own host and nothing else; across a thousand addresses
one broken host must not abort the sweep.

The pool takes a finished host list rather than a CIDR. What may be scanned
is policy and stays in the API layer, which is also what makes the test
below possible: it drives the real probe over a real socket against three
loopback stubs (Tasmota, 401, foreign JSON), and the policy forbids
loopback. A test that mocked probe_host would only prove that a thread pool
calls a function — the blind spot that let #126 ship.
MSG
```

---

### Task 3: mDNS browse and the dependency

**Files:**
- Modify: `app/tasmota/discovery.py`, `requirements.txt`
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `browse_mdns(duration: float = 4.0) -> list[dict]`, `MdnsUnavailable` exception.

- [ ] **Step 1: Add the dependency**

Append to `requirements.txt` after `watchdog>=6.0.0`:

```
zeroconf>=0.149.12
```

The floor is mandatory, not stylistic: everything below 0.149.12 carries GHSA-9663-mqmp-p9mm (CVE-2026-48045), an unbounded TC-deferred queue that lets any host on the local link exhaust memory through spoofed mDNS floods.

Run: `uv pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

```python
def test_browse_mdns_raises_when_zeroconf_is_missing(monkeypatch):
    monkeypatch.setattr(discovery, "_import_zeroconf", lambda: None)
    with pytest.raises(discovery.MdnsUnavailable):
        discovery.browse_mdns(duration=0.01)


def test_service_info_becomes_a_finding():
    """The browse callback's translation step, tested without a network."""
    class FakeInfo:
        parsed_addresses = staticmethod(lambda: ["192.168.1.42"])
        server = "tasmota-1234.local."
        properties = {b"friendly_name": b"Hallway Light", b"module": b"Sonoff Basic"}

    entry = discovery.service_info_to_finding(FakeInfo())
    assert entry["ip"] == "192.168.1.42"
    assert entry["hostname"] == "tasmota-1234"
    assert entry["friendly_name"] == "Hallway Light"
    assert entry["requires_auth"] is False


def test_service_info_without_an_address_is_skipped():
    class FakeInfo:
        parsed_addresses = staticmethod(lambda: [])
        server = "ghost.local."
        properties = {}

    assert discovery.service_info_to_finding(FakeInfo()) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_discovery.py -o addopts="" -v -k mdns or service_info`
Expected: FAIL — `AttributeError: ... has no attribute 'MdnsUnavailable'`

- [ ] **Step 4: Implement the browse**

Append to `app/tasmota/discovery.py`:

```python
import time

# Tasmota announces itself over the generic HTTP service; some builds add a
# dedicated one. Browsing both costs nothing and catches both.
MDNS_SERVICES = ("_http._tcp.local.", "_tasmota._tcp.local.")


class MdnsUnavailable(RuntimeError):
    """zeroconf is not installed or could not be started."""


def _import_zeroconf():
    """Import zeroconf lazily so a missing package fails only the mDNS path.

    Separated into its own function so a test can replace it — the scan path
    must stay usable even where mDNS cannot work at all.
    """
    try:
        import zeroconf  # noqa: PLC0415 - deliberate lazy import
        return zeroconf
    except ImportError:
        return None


def _decode(value: Any) -> Optional[str]:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else None


def service_info_to_finding(info: Any) -> Optional[dict[str, Any]]:
    """Translate one announced service into a finding.

    mDNS carries far less than ``Status 0``: an address, a name, and whatever
    the device chose to put into its TXT record. The missing fields stay None
    rather than being guessed — the UI shows what is known.
    """
    addresses = info.parsed_addresses() if callable(getattr(info, "parsed_addresses", None)) else []
    if not addresses:
        return None

    properties = getattr(info, "properties", None) or {}
    decoded = {_decode(key): _decode(value) for key, value in properties.items()}

    hostname = (getattr(info, "server", "") or "").rstrip(".")
    if hostname.endswith(".local"):
        hostname = hostname[: -len(".local")]

    return {
        "ip": addresses[0],
        "hostname": hostname or None,
        "friendly_name": decoded.get("friendly_name") or decoded.get("devicename"),
        "module": decoded.get("module"),
        "firmware_version": decoded.get("version"),
        "mac": decoded.get("mac"),
        "requires_auth": False,
    }


def browse_mdns(duration: float = 4.0) -> list[dict[str, Any]]:
    """Collect devices that announce themselves for ``duration`` seconds.

    Passive: this listens, it does not probe anything. In a bridge-network
    container it will find nothing at all — multicast does not cross the
    bridge — and that is a fact about the deployment, not an error here. The
    caller is responsible for saying so.
    """
    module = _import_zeroconf()
    if module is None:
        raise MdnsUnavailable(
            "mDNS discovery needs the 'zeroconf' package, which is not installed."
        )

    found: dict[str, dict[str, Any]] = {}

    def _on_change(zc, service_type, name, state_change, **kwargs):
        if state_change is not module.ServiceStateChange.Added:
            return
        info = zc.get_service_info(service_type, name, timeout=1000)
        if info is None:
            return
        entry = service_info_to_finding(info)
        if entry:
            found.setdefault(entry["ip"], entry)

    zc = module.Zeroconf()
    try:
        browser = module.ServiceBrowser(zc, list(MDNS_SERVICES), handlers=[_on_change])
        time.sleep(duration)
        browser.cancel()
    finally:
        zc.close()

    return list(found.values())
```

- [ ] **Step 5: Run the whole discovery test file**

Run: `pytest tests/test_discovery.py -o addopts="" -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add app/tasmota/discovery.py tests/test_discovery.py requirements.txt
git commit -F- <<'MSG'
feat(discovery): browse mDNS for devices that announce themselves

Browses both `_http._tcp` and `_tasmota._tcp`; Tasmota uses the generic
service and some builds add the dedicated one. mDNS carries far less than a
Status 0 answer, so the unknown fields stay null instead of being guessed.

zeroconf is imported lazily behind its own function, so a missing package
fails the mDNS path alone and leaves the scan path — the one that works
everywhere — untouched.

Dependency vetting for zeroconf: OSV clean at 0.150.0, first released
2014-07-08, 262 versions, maintained by the python-zeroconf org, no
typosquat lookalikes. The `>=0.149.12` floor is required rather than
cosmetic: earlier versions carry GHSA-9663-mqmp-p9mm (CVE-2026-48045), an
unbounded TC-deferred queue that lets any host on the local link exhaust
memory through spoofed mDNS floods — this feature's own threat model.
MSG
```

---

### Task 4: A second job kind, without the deadlock

**Files:**
- Modify: `app/tasmota/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `discovery.browse_mdns()`, `discovery.scan_network()`, `discovery.MdnsUnavailable` from Tasks 2–3.
- Produces: `create_discovery_job(method: str, hosts: list[str] | None, *, runner=None, clock=time.time, background=True) -> str | None`. Returns None when a discovery job is already running. Every job dict now carries `kind`.

The trap this task exists to avoid: `batch_in_progress()` and the exclusivity check inside `create_batch_job()` currently scan **all** jobs in the store. Adding a second kind without scoping them means a running scan silently blocks every batch update, and vice versa.

- [ ] **Step 1: Write the failing regression test**

Append to `tests/test_jobs.py`:

```python
def test_a_running_discovery_job_does_not_block_a_batch_update():
    """The deadlock this design had to sidestep.

    Both kinds share one store. If the batch exclusivity check keeps looking
    at every job in it, a scan blocks every update for as long as it runs —
    silently, and only in production where scans are slow.
    """
    jobs._reset_for_tests()

    def slow_scan(on_progress):
        time.sleep(0.2)
        return []

    discovery_id = jobs.create_discovery_job("scan", ["192.0.2.1"], runner=slow_scan)
    assert discovery_id is not None

    batch_id = jobs.create_batch_job(
        [{"ip": "192.0.2.9"}], check_only=True, update_only_needed=False,
        global_timeout=None, updater=lambda cfg, check_only=False: {"success": True},
        background=False,
    )
    assert batch_id is not None, "a running scan must not block a batch update"
    assert jobs.get_job(batch_id)["kind"] == "batch"
    assert jobs.get_job(discovery_id)["kind"] == "discovery"


def test_only_one_discovery_job_runs_at_a_time():
    jobs._reset_for_tests()

    def slow_scan(on_progress):
        time.sleep(0.2)
        return []

    assert jobs.create_discovery_job("scan", ["192.0.2.1"], runner=slow_scan) is not None
    assert jobs.create_discovery_job("scan", ["192.0.2.2"], runner=slow_scan) is None


def test_discovery_job_records_results_and_progress():
    jobs._reset_for_tests()
    finding = {"ip": "192.0.2.5", "requires_auth": False}

    def runner(on_progress):
        on_progress(1, 1)
        return [finding]

    job_id = jobs.create_discovery_job("scan", ["192.0.2.5"], runner=runner, background=False)
    job = jobs.get_job(job_id)
    assert job["status"] == "completed"
    assert job["results"] == [finding]
    assert job["completed"] == 1 and job["total"] == 1


def test_mdns_job_without_zeroconf_ends_as_error():
    jobs._reset_for_tests()

    def runner(on_progress):
        raise discovery.MdnsUnavailable("no zeroconf here")

    job_id = jobs.create_discovery_job("mdns", None, runner=runner, background=False)
    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert "zeroconf" in job["error"]
```

Add `import time` and `from app.tasmota import discovery` to the file's imports if they are not there yet.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_jobs.py -o addopts="" -v`
Expected: FAIL — `AttributeError: module 'app.tasmota.jobs' has no attribute 'create_discovery_job'`

- [ ] **Step 3: Scope the existing exclusivity to batch jobs**

In `app/tasmota/jobs.py`, change `batch_in_progress()`:

```python
def batch_in_progress() -> bool:
    with _lock:
        return _kind_in_progress_locked("batch")


def _kind_in_progress_locked(kind: str) -> bool:
    """Is a job of this kind pending or running? Caller holds the lock.

    Scoped by kind on purpose: discovery and batch updates share one store,
    and an unscoped check would let a running scan block every update.
    """
    return any(
        job["status"] in ("pending", "running") and job.get("kind") == kind
        for job in _jobs.values()
    )
```

In `create_batch_job()`, replace the exclusivity check and add the field:

```python
    with _lock:
        if _kind_in_progress_locked("batch"):
            return None
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {
            "job_id": job_id,
            "kind": "batch",
            "status": "pending",
            ...
```

(Keep every other key in that dict exactly as it is.)

- [ ] **Step 4: Add the discovery job**

Append to `app/tasmota/jobs.py`:

```python
def create_discovery_job(
    method: str,
    hosts: Optional[List[str]],
    *,
    runner: Optional[Callable[..., List[Dict[str, Any]]]] = None,
    clock: Callable[[], float] = time.time,
    background: bool = True,
) -> Optional[str]:
    """Create and start a discovery job. Returns its id, or None if one runs.

    ``runner`` receives a single ``on_progress(completed, total)`` callback and
    returns the findings; it is injectable so the job mechanics can be tested
    without touching the network.
    """
    resolved = runner or _default_discovery_runner(method, hosts)
    with _lock:
        if _kind_in_progress_locked("discovery"):
            return None
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {
            "job_id": job_id,
            "kind": "discovery",
            "method": method,
            "status": "pending",
            "total": len(hosts) if hosts is not None else None,
            "completed": 0,
            "results": [],
            "notice": None,
            "error": None,
            "created_at": clock(),
            "finished_at": None,
        }
        _prune_locked()

    if background:
        threading.Thread(target=_run_discovery, args=(job_id, resolved, clock), daemon=True).start()
    else:
        _run_discovery(job_id, resolved, clock)
    return job_id


def _default_discovery_runner(method: str, hosts: Optional[List[str]]):
    """Bind the core function this method needs, without importing at module load."""
    from app.tasmota import discovery

    if method == "mdns":
        return lambda on_progress: discovery.browse_mdns()
    return lambda on_progress: discovery.scan_network(hosts or [], on_progress=on_progress)


NO_MDNS_ANSWER = (
    "No device announced itself. In a bridge-network container mDNS cannot "
    "work at all, because multicast does not cross the bridge — see the "
    "container setup documentation."
)


def _run_discovery(
    job_id: str,
    runner: Callable[..., List[Dict[str, Any]]],
    clock: Callable[[], float],
) -> None:
    from app.tasmota import discovery

    try:
        _set(job_id, status="running")

        def on_progress(completed: int, total: int) -> None:
            _set(job_id, completed=completed, total=total)

        results = runner(on_progress)

        notice = None
        with _lock:
            job = _jobs.get(job_id)
            method = job.get("method") if job else None
        if not results and method == "mdns":
            notice = NO_MDNS_ANSWER

        _set(job_id, status="completed", results=list(results), notice=notice,
             finished_at=clock())
    except discovery.MdnsUnavailable as exc:
        _set(job_id, status="error", error=str(exc), finished_at=clock())
    except Exception as exc:  # pragma: no cover - defensive; surfaced to the client
        _set(job_id, status="error", error=str(exc), finished_at=clock())
```

- [ ] **Step 5: Run the job tests to verify they pass**

Run: `pytest tests/test_jobs.py tests/test_jobs_api.py -o addopts="" -v`
Expected: PASS, including the four new tests

- [ ] **Step 6: Run the green core to catch fallout**

Run: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/tasmota/jobs.py tests/test_jobs.py
git commit -F- <<'MSG'
feat(jobs): carry a second job kind without blocking batch updates

Discovery reuses the batch job pattern — 202 with a job id, polled through
GET /api/jobs/<id> — because a /22 scan takes about 25s and the single
gthread worker would otherwise be blocked for all of it.

Both kinds share one store, so the exclusivity checks had to become
kind-scoped. Unscoped they would have let a running scan silently block
every batch update, and only in production where scans are slow enough to
notice. A regression test pins both directions.

An mDNS run that finds nothing completes with a notice saying multicast
cannot cross a container bridge, rather than claiming no devices exist —
the same honesty line as isVersionComparisonKnown() in #91.
MSG
```

---

### Task 5: The endpoints and the scan policy

**Files:**
- Modify: `app/tasmota/api.py`
- Test: `tests/test_discovery_api.py` (create)

**Interfaces:**
- Consumes: `jobs.create_discovery_job()` from Task 4, `discovery.hosts_in_network()` from Task 2.
- Produces: `validate_scan_target(value: str) -> ipaddress.IPv4Network` (raises `ValidationError`), `suggest_local_networks() -> list[str]`, routes `GET`/`POST /api/discovery`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_discovery_api.py`:

```python
"""Contract tests for the discovery endpoints."""
import pytest
from marshmallow import ValidationError

from app.tasmota import api, jobs
from server import create_app

MAX_PREFIX = 22


@pytest.fixture
def client():
    app = create_app()
    app.config.update({"TESTING": True})
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["ui_authenticated"] = True
        yield client


@pytest.mark.parametrize("value", [
    "192.168.1.0/24", "10.0.0.0/24", "172.16.5.0/23", "192.168.0.0/22",
])
def test_private_networks_within_the_limit_are_accepted(value):
    assert str(api.validate_scan_target(value)) == value


@pytest.mark.parametrize("value,reason", [
    ("8.8.8.0/24", "public"),
    ("127.0.0.0/24", "loopback"),
    ("169.254.0.0/24", "link-local"),
    ("224.0.0.0/24", "multicast"),
    ("192.168.0.0/16", "too large"),
    ("not-a-network", "garbage"),
    ("fd00::/64", "IPv6"),
    ("", "empty"),
])
def test_targets_outside_the_fence_are_rejected(value, reason):
    with pytest.raises(ValidationError):
        api.validate_scan_target(value)


def test_get_discovery_offers_a_suggestion_and_the_limits(client):
    response = client.get("/api/discovery")
    assert response.status_code == 200
    body = response.get_json()
    assert body["limits"] == {"max_prefix": MAX_PREFIX, "max_hosts": 1024}
    assert isinstance(body["suggested_networks"], list)


def test_post_scan_starts_a_job(client, monkeypatch):
    monkeypatch.setattr(jobs, "create_discovery_job", lambda *a, **kw: "job-1")
    response = client.post("/api/discovery",
                           json={"method": "scan", "network": "192.168.1.0/24"})
    assert response.status_code == 202
    assert response.get_json()["job_id"] == "job-1"


def test_post_mdns_starts_a_job(client, monkeypatch):
    monkeypatch.setattr(jobs, "create_discovery_job", lambda *a, **kw: "job-2")
    response = client.post("/api/discovery", json={"method": "mdns"})
    assert response.status_code == 202


def test_post_rejects_a_public_network_with_a_reason(client):
    response = client.post("/api/discovery",
                           json={"method": "scan", "network": "8.8.8.0/24"})
    assert response.status_code == 400
    assert "private" in response.get_json()["details"].lower()


def test_post_reports_a_running_job_as_conflict(client, monkeypatch):
    monkeypatch.setattr(jobs, "create_discovery_job", lambda *a, **kw: None)
    response = client.post("/api/discovery",
                           json={"method": "scan", "network": "192.168.1.0/24"})
    assert response.status_code == 409


def test_post_requires_json(client):
    response = client.post("/api/discovery", data="method=scan",
                           content_type="application/x-www-form-urlencoded")
    assert response.status_code == 415


def test_post_rejects_an_unknown_method(client):
    response = client.post("/api/discovery", json={"method": "arp-spoof"})
    assert response.status_code == 400


def test_discovery_is_behind_the_auth_gate():
    """Fail-closed, like every other /api/* route."""
    app = create_app()
    app.config.update({"TESTING": True})
    with app.test_client() as anonymous:
        assert anonymous.get("/api/discovery").status_code == 401
        assert anonymous.post("/api/discovery", json={"method": "mdns"}).status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_discovery_api.py -o addopts="" -v`
Expected: FAIL — `AttributeError: module 'app.tasmota.api' has no attribute 'validate_scan_target'`

- [ ] **Step 3: Implement the policy and the resource**

Add to the imports at the top of `app/tasmota/api.py`:

```python
import ipaddress
import socket

from app.tasmota import discovery
```

Add before `class DiscoveryResource`:

```python
# A /22 is 1024 addresses — about 25 seconds at 64 workers. Wide enough for any
# home network, narrow enough that the endpoint cannot be turned into a sweep.
MAX_SCAN_PREFIX = 22
MAX_SCAN_HOSTS = 1024


def validate_scan_target(value: str) -> ipaddress.IPv4Network:
    """Decide whether a network may be scanned at all.

    Deliberately stricter than ``is_valid_ip_address()``, which allows public
    addresses because a device may legitimately sit on one. A *scan* is a
    different matter: an endpoint that sweeps arbitrary public ranges is a port
    scanner behind someone's session cookie. Private IPv4 only, and bounded.
    """
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except (ValueError, AttributeError) as exc:
        raise ValidationError(f"Not a usable network: {value!r}") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValidationError("Only IPv4 networks can be scanned.")
    if not network.is_private:
        raise ValidationError(
            "Only private networks can be scanned, so the scanner cannot be "
            "pointed at the public internet."
        )
    if network.is_loopback or network.is_link_local or network.is_multicast:
        raise ValidationError("Loopback, link-local and multicast ranges cannot be scanned.")
    if network.prefixlen < MAX_SCAN_PREFIX:
        raise ValidationError(
            f"Network is too large: /{network.prefixlen} exceeds the /{MAX_SCAN_PREFIX} "
            f"limit of {MAX_SCAN_HOSTS} addresses."
        )
    return network


def suggest_local_networks() -> list[str]:
    """Guess the local network, to prefill the scan field.

    A UDP socket that is 'connected' to an arbitrary address reveals which
    interface would carry the traffic, without sending a packet. It reveals the
    address, not its prefix length — /24 is an assumption, which is exactly why
    the API calls this a suggestion and the UI keeps the field editable.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, guaranteed unrouted
        local_ip = probe.getsockname()[0]
    except OSError:
        return []
    finally:
        probe.close()

    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return []
    return [str(network)] if network.is_private else []


class DiscoveryResource(Resource):
    """Find Tasmota devices on the network. Never writes anything."""

    def get(self):
        """
        Get scan suggestions and limits
        ---
        tags:
          - discovery
        responses:
          200:
            description: A suggested network to scan and the enforced limits
            examples:
              application/json:
                suggested_networks: ["192.168.1.0/24"]
                limits: {max_prefix: 22, max_hosts: 1024}
        """
        return {
            "suggested_networks": suggest_local_networks(),
            "limits": {"max_prefix": MAX_SCAN_PREFIX, "max_hosts": MAX_SCAN_HOSTS},
        }

    def post(self):
        """
        Start a discovery job
        ---
        tags:
          - discovery
        parameters:
          - in: body
            name: body
            required: true
            schema:
              properties:
                method:
                  type: string
                  enum: [mdns, scan]
                network:
                  type: string
                  description: Required for method=scan. Private IPv4, prefix >= 22.
            examples:
              scan: {method: scan, network: "192.168.1.0/24"}
              mdns: {method: mdns}
        responses:
          202:
            description: Job accepted; poll GET /api/jobs/{job_id}
            examples:
              application/json: {job_id: "3f2a…", status_url: "/api/jobs/3f2a…"}
          400:
            description: Unknown method, or a network outside the allowed range
          409:
            description: A discovery job is already running
          415:
            description: Body was not JSON
        """
        if not request.is_json:
            return {'error': 'Unsupported Media Type',
                    'details': 'Content-Type must be application/json'}, 415

        body = request.get_json(silent=True) or {}
        method = body.get('method')
        if method not in ('mdns', 'scan'):
            return {'error': 'Bad Request',
                    'details': "'method' must be 'mdns' or 'scan'"}, 400

        hosts = None
        if method == 'scan':
            try:
                network = validate_scan_target(body.get('network') or '')
            except ValidationError as exc:
                return {'error': 'Bad Request', 'details': str(exc.messages[0])
                        if isinstance(exc.messages, list) else str(exc.messages)}, 400
            hosts = discovery.hosts_in_network(network)
            current_app.logger.info(
                "Discovery scan requested for %s (%d hosts)", network, len(hosts)
            )
        else:
            current_app.logger.info("Discovery via mDNS requested")

        job_id = jobs.create_discovery_job(method, hosts)
        if job_id is None:
            return {'error': 'A discovery job is already in progress'}, 409
        return {'job_id': job_id, 'status_url': f'/api/jobs/{job_id}'}, 202
```

In `init_api()`, register the route next to the others:

```python
    api.add_resource(DiscoveryResource, '/api/discovery')
```

- [ ] **Step 4: Mark already-configured findings**

Discovery results must show which devices are already in the configuration. Extend `JobResource.get()` in `app/tasmota/api.py`, right before `return job`:

```python
        if job.get("kind") == "discovery" and job.get("results"):
            devices_file = current_app.config.get('DEVICES_FILE', 'devices.yaml')
            known = {
                device.get("ip")
                for device in load_devices_from_file(str(devices_file))
            }
            # load_devices_from_file() answers every failure with an empty list.
            # For a display flag that is harmless — a known device would show up
            # as new. It must never be used as a write baseline, and is not.
            job["results"] = [
                {**entry, "already_configured": entry.get("ip") in known}
                for entry in job["results"]
            ]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_discovery_api.py -o addopts="" -v`
Expected: PASS (all cases)

- [ ] **Step 6: Run the green core**

Run: `pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/tasmota/api.py tests/test_discovery_api.py
git commit -F- <<'MSG'
feat(api): expose discovery behind a fenced scan policy

validate_scan_target() is deliberately stricter than is_valid_ip_address():
that one allows public addresses because a device may legitimately sit on
one, but a *scan* endpoint that sweeps arbitrary public ranges is a port
scanner behind someone's session cookie. Private IPv4 only, prefix >= /22,
no loopback, link-local or multicast.

The scan target is a UI field rather than an env variable, so the fence is
enforced server-side where it cannot be edited away. GET /api/discovery
prefills it from the local interface address; the prefix length is not
knowable that way, so /24 is an assumption and the field is named
suggested_networks to say so.

Findings are flagged already_configured through the read path, whose
empty-list-on-failure behaviour is harmless for a display flag and is never
used as a write baseline. Discovery has no write path at all.
MSG
```

---

### Task 6: The discovery modal

**Files:**
- Create: `app/static/js/discovery.js`
- Modify: `app/templates/index.html`, `app/static/js/devices-editor.js`

**Interfaces:**
- Consumes: `GET`/`POST /api/discovery` and `GET /api/jobs/<id>` from Tasks 4–5.
- Produces: Alpine component `discoveryModal()`; emits a `discovery-adopt` CustomEvent whose `detail.devices` is a list of `{ip, dns_name}` objects for the editor.

- [ ] **Step 1: Write the component**

Create `app/static/js/discovery.js`:

```javascript
/**
 * Find Tasmota devices on the network and hand the picks to the editor.
 *
 * This component never writes configuration. Adopted devices leave here as a
 * `discovery-adopt` event and become unsaved rows in the editor, so the single
 * save path through PUT /api/config/devices stays the only writer.
 */
function discoveryModal() {
    return {
        isOpen: false,
        method: null,          // 'mdns' | 'scan' while a job runs
        network: '',
        limits: { max_prefix: 22, max_hosts: 1024 },
        jobId: null,
        status: null,          // 'pending' | 'running' | 'completed' | 'error'
        completed: 0,
        total: null,
        results: [],
        selected: [],
        notice: null,
        error: null,
        pollTimer: null,

        async open() {
            this.isOpen = true;
            this.reset();
            try {
                const response = await fetch('/api/discovery');
                if (response.ok) {
                    const body = await response.json();
                    this.limits = body.limits || this.limits;
                    this.network = (body.suggested_networks || [])[0] || '';
                }
            } catch (err) {
                // A missing suggestion is not worth an error banner — the user
                // can type the network. Only a failed *scan* is worth shouting about.
            }
        },

        close() {
            // Stops the polling, not the job. The server finishes on its own
            // within ~25s; cancelling it would be extra state for nothing.
            this.isOpen = false;
            this.stopPolling();
        },

        reset() {
            this.jobId = null;
            this.status = null;
            this.completed = 0;
            this.total = null;
            this.results = [];
            this.selected = [];
            this.notice = null;
            this.error = null;
        },

        get isRunning() {
            return this.status === 'pending' || this.status === 'running';
        },

        get progressLabel() {
            if (this.method === 'mdns') return 'Listening for announcements…';
            if (this.total) return `Probed ${this.completed} of ${this.total} addresses`;
            return 'Starting…';
        },

        get adoptableResults() {
            return this.results.filter(device => !device.already_configured);
        },

        async start(method) {
            this.reset();
            this.method = method;
            const payload = method === 'scan'
                ? { method, network: this.network }
                : { method };

            try {
                const response = await fetch('/api/discovery', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await response.json();
                if (!response.ok) {
                    this.error = body.details || body.error || 'Discovery could not be started.';
                    return;
                }
                this.jobId = body.job_id;
                this.status = 'pending';
                this.poll();
            } catch (err) {
                this.error = 'Discovery could not be started.';
            }
        },

        poll() {
            this.pollTimer = setInterval(async () => {
                try {
                    const response = await fetch(`/api/jobs/${this.jobId}`);
                    if (!response.ok) {
                        this.error = 'Lost track of the discovery job.';
                        this.stopPolling();
                        return;
                    }
                    const job = await response.json();
                    this.status = job.status;
                    this.completed = job.completed || 0;
                    this.total = job.total;
                    this.results = job.results || [];
                    this.notice = job.notice;
                    if (job.status === 'completed' || job.status === 'error') {
                        this.error = job.error;
                        this.stopPolling();
                    }
                } catch (err) {
                    this.error = 'Lost track of the discovery job.';
                    this.stopPolling();
                }
            }, 1000);
        },

        stopPolling() {
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
        },

        toggle(ip) {
            const index = this.selected.indexOf(ip);
            if (index === -1) this.selected.push(ip);
            else this.selected.splice(index, 1);
        },

        adopt() {
            const picks = this.results
                .filter(device => this.selected.includes(device.ip))
                .map(device => ({ ip: device.ip, dns_name: device.hostname || '' }));
            this.$dispatch('discovery-adopt', { devices: picks });
            this.close();
        },
    };
}
```

- [ ] **Step 2: Add the markup**

In `app/templates/index.html`, inside the device editor section, add the trigger button:

```html
<button class="button is-info"
        data-testid="open-discovery"
        title="Find Tasmota devices on your network and add them to this list"
        @click="$refs.discovery.open()">
    <span>Find devices</span>
</button>
```

And the modal, as a sibling of the editor markup:

```html
<div x-data="discoveryModal()" x-ref="discovery" class="modal"
     :class="{ 'is-active': isOpen }" data-testid="discovery-modal">
  <div class="modal-background" @click="close()"></div>
  <div class="modal-card">
    <header class="modal-card-head">
      <p class="modal-card-title">Find devices</p>
      <button class="delete" aria-label="Close this dialog" @click="close()"></button>
    </header>
    <section class="modal-card-body">

      <div class="buttons">
        <button class="button" data-testid="start-mdns" :disabled="isRunning"
                title="Listen for devices that announce themselves via mDNS"
                @click="start('mdns')">Search via mDNS</button>
      </div>

      <div class="field has-addons">
        <div class="control is-expanded">
          <input class="input" type="text" x-model="network"
                 data-testid="scan-network"
                 :placeholder="`e.g. 192.168.1.0/24 (max /${limits.max_prefix})`"
                 aria-label="Network to scan in CIDR notation">
        </div>
        <div class="control">
          <button class="button is-warning" data-testid="start-scan" :disabled="isRunning"
                  title="Scan this network — sends one HTTP request to every address in the range"
                  @click="start('scan')">Scan network</button>
        </div>
      </div>

      <div x-show="isRunning" aria-live="polite" data-testid="discovery-progress">
        <p x-text="progressLabel"></p>
        <progress class="progress is-small is-info"
                  :value="total ? completed : null" :max="total || 100"></progress>
      </div>

      <div class="notification is-warning" x-show="notice" data-testid="discovery-notice"
           aria-live="polite" x-text="notice"></div>
      <div class="notification is-danger" x-show="error" data-testid="discovery-error"
           aria-live="assertive" x-text="error"></div>

      <table class="table is-fullwidth" x-show="results.length"
             data-testid="discovery-results">
        <thead>
          <tr><th></th><th>Address</th><th>Name</th><th>Firmware</th><th></th></tr>
        </thead>
        <tbody>
          <template x-for="device in results" :key="device.ip">
            <tr>
              <td>
                <input type="checkbox" :value="device.ip"
                       :disabled="device.already_configured"
                       :aria-label="`Select ${device.ip} for adoption`"
                       @change="toggle(device.ip)">
              </td>
              <td x-text="device.ip"></td>
              <td x-text="device.friendly_name || device.hostname || '—'"></td>
              <td x-text="device.firmware_version || '—'"></td>
              <td>
                <span class="tag is-light" x-show="device.already_configured">Already in list</span>
                <span class="tag is-warning" x-show="device.requires_auth"
                      title="This device is password-protected — add credentials after adopting it">
                  Credentials needed
                </span>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <p x-show="status === 'completed' && !results.length && !notice"
         data-testid="discovery-empty">No Tasmota devices answered in this range.</p>

    </section>
    <footer class="modal-card-foot">
      <button class="button is-primary" data-testid="adopt-selected"
              :disabled="!selected.length"
              title="Add the selected devices to the editor — nothing is saved until you press Save"
              @click="adopt()">Add selected to list</button>
      <button class="button" title="Close this dialog and stop watching the search"
              @click="close()">Close</button>
    </footer>
  </div>
</div>
```

Register the script next to the existing ones:

```html
<script src="{{ url_for('static', filename='js/discovery.js') }}"></script>
```

- [ ] **Step 3: Receive the findings in the editor**

In `app/static/js/devices-editor.js`, add a handler that appends adopted devices as unsaved rows. Add this method to the editor component, matching the naming of the methods already there:

```javascript
        /**
         * Take findings from the discovery modal as unsaved rows.
         *
         * Deliberately additive and deliberately unsaved: the user still has to
         * add credentials and press Save, so PUT /api/config/devices remains the
         * only path that writes the file.
         */
        adoptDiscovered(devices) {
            const known = new Set(this.devices.map(device => device.ip));
            devices
                .filter(device => !known.has(device.ip))
                .forEach(device => {
                    this.devices.push({
                        ip: device.ip,
                        dns_name: device.dns_name || '',
                        username: '',
                        password: '',
                        timeout: null,
                        has_password: false,
                    });
                });
            this.isDirty = true;
        },
```

Wire the event on the editor's root element in `index.html`:

```html
@discovery-adopt.window="adoptDiscovered($event.detail.devices)"
```

Check the editor component's existing property names first (`devices`, `isDirty`) and match whatever is actually there — this snippet assumes them.

- [ ] **Step 4: Verify by hand**

Run: `ENV_FILE=.env.dev python server.py`
Open `http://localhost:5001`, press "Find devices", run a scan against your own network, adopt a device, confirm it appears as an unsaved row and that pressing Save writes it.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/discovery.js app/static/js/devices-editor.js app/templates/index.html
git commit -F- <<'MSG'
feat(ui): add the discovery modal and adopt findings into the editor

Two explicit actions rather than one clever button: mDNS is a single click,
the scan needs a network and says in its tooltip that it sends a request to
every address in the range. Nothing starts on its own, not even when the
dialog opens.

The scan shows a real progress bar from completed/total; mDNS shows a
spinner, because no total exists there and inventing one would be a lie.
Devices already in the configuration are shown but not selectable, and
password-protected finds are tagged rather than retried with credentials.

Adoption dispatches an event and appends unsaved rows; the modal never
writes. Closing it stops the polling, not the job — hence "Close" rather
than "Cancel".
MSG
```

---

### Task 7: End-to-end coverage

**Files:**
- Create: `tests/e2e/test_discovery.py`

**Interfaces:**
- Consumes: the markup and `data-testid` hooks from Task 6.
- Produces: nothing other tasks depend on.

The job is stubbed through `page.route` rather than scanned for real: the e2e run must not depend on what happens to be on the CI runner's network, and a real scan would take 25 seconds per test.

- [ ] **Step 1: Write the tests**

Create `tests/e2e/test_discovery.py`:

```python
"""End-to-end coverage for the discovery modal."""
import json

import pytest

pytestmark = pytest.mark.e2e

FINDINGS = [
    {"ip": "192.168.100.150", "hostname": "tasmota-new", "friendly_name": "Attic",
     "module": "ESP8266EX", "firmware_version": "14.2.0", "mac": "AA:BB:CC:DD:EE:01",
     "requires_auth": False, "already_configured": False},
    {"ip": "192.168.100.101", "hostname": "known", "friendly_name": "Known one",
     "module": "ESP8266EX", "firmware_version": "13.0.0", "mac": "AA:BB:CC:DD:EE:02",
     "requires_auth": False, "already_configured": True},
]


def _stub_discovery(page, results, notice=None, status="completed"):
    page.route("**/api/discovery", lambda route: route.fulfill(
        status=202, content_type="application/json",
        body=json.dumps({"job_id": "stub", "status_url": "/api/jobs/stub"}),
    ) if route.request.method == "POST" else route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"suggested_networks": ["192.168.100.0/24"],
                         "limits": {"max_prefix": 22, "max_hosts": 1024}}),
    ))
    page.route("**/api/jobs/stub", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"job_id": "stub", "kind": "discovery", "method": "scan",
                         "status": status, "completed": 254, "total": 254,
                         "results": results, "notice": notice, "error": None}),
    ))


def test_scan_lists_findings_and_marks_known_devices(page, app_server):
    _stub_discovery(page, FINDINGS)
    page.goto(app_server)
    page.click('[data-testid="open-discovery"]')
    page.click('[data-testid="start-scan"]')

    results = page.locator('[data-testid="discovery-results"]')
    results.wait_for(state="visible")
    assert results.locator("tbody tr").count() == 2

    known_row = results.locator("tbody tr", has_text="192.168.100.101")
    assert known_row.locator("input[type=checkbox]").is_disabled()


def test_adopting_a_finding_adds_an_unsaved_row(page, app_server):
    _stub_discovery(page, FINDINGS)
    page.goto(app_server)
    page.click('[data-testid="open-discovery"]')
    page.click('[data-testid="start-scan"]')
    page.locator('[data-testid="discovery-results"]').wait_for(state="visible")

    page.locator('input[value="192.168.100.150"]').check()
    page.click('[data-testid="adopt-selected"]')

    # x-show only toggles display, so assert visibility, never count == 0.
    page.locator('[data-testid="discovery-modal"]').wait_for(state="hidden")
    assert page.locator('input[value="192.168.100.150"]').count() >= 1


def test_an_empty_mdns_run_explains_itself(page, app_server):
    _stub_discovery(page, [], notice="No device announced itself. In a bridge-network "
                                     "container mDNS cannot work at all")
    page.goto(app_server)
    page.click('[data-testid="open-discovery"]')
    page.click('[data-testid="start-mdns"]')

    notice = page.locator('[data-testid="discovery-notice"]')
    notice.wait_for(state="visible")
    assert "bridge-network" in notice.inner_text()
```

Check `tests/e2e/conftest.py` for the actual fixture name and signature before running — this assumes an `app_server` fixture that yields the base URL, matching the session-scoped fixture the suite already uses.

- [ ] **Step 2: Run the discovery e2e tests**

Run: `pytest tests/e2e/test_discovery.py -m e2e -o addopts="" -v`
Expected: PASS

- [ ] **Step 3: Run the whole e2e suite**

Run: `GITHUB_TOKEN=$(gh auth token) pytest tests/e2e -m e2e -o addopts=""`
Expected: PASS. New markup breaks existing tests through Playwright strict-mode ambiguity, so the full suite is the gate — not just the new file. Without the token the app hits GitHub's 60 req/h limit and the update-flow tests fail with a misleading timeout.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_discovery.py
git commit -m "test(e2e): cover the discovery modal, adoption and the empty-mDNS notice"
```

---

### Task 8: Documentation

**Files:**
- Modify: `docs/container-setup.md`, `docs/api.md`, `docs/web-interface.md`, `docs/configuration.md`, `docs/contributing.md`, `README.md`

- [ ] **Step 1: Document the mDNS deployment trade-off**

In `docs/container-setup.md`, add a section explaining that mDNS needs `network_mode: host`, with a second compose variant and an honest list of what that costs (no network isolation, no port mapping, the container shares the host's network stack). State plainly that the IP range scan works in the default bridge setup and that mDNS in a bridge container finds nothing — not because of a bug, but because multicast does not cross the bridge.

- [ ] **Step 2: Document the endpoints**

In `docs/api.md`, add `GET /api/discovery` and `POST /api/discovery` with request and response examples matching the Swagger docstrings from Task 5, plus the polling flow through `GET /api/jobs/<id>` and the `kind: "discovery"` result shape.

- [ ] **Step 3: Document the workflow and the limits**

In `docs/web-interface.md`, describe the modal: two explicit actions, adoption into the editor, and that nothing is saved until Save is pressed.

In `docs/configuration.md`, document the scan limits (private IPv4 only, prefix ≥ /22, 64 concurrent probes, 1.5 s timeout) and state explicitly that discovery introduces **no** new environment variable.

- [ ] **Step 4: Retire the backlog entry**

In `docs/contributing.md`, remove "Device Discovery" from *Areas for Improvement* — it ships here.

- [ ] **Step 5: Check the README**

Run: `grep -c '^```' README.md` (must be even). Verify badges, clone URL, ports, commands, and that no deprecated path is presented as current. Add discovery to the feature list if the README enumerates features. Remember the image is `dodjango/tasmota-updater` while the git repo is `dodjango/tasmota-auto-updater` — do not "correct" either into the other.

- [ ] **Step 6: Verify the docs build**

Run: `mkdocs build --strict`
Expected: PASS, no broken links.

- [ ] **Step 7: Commit**

```bash
git add docs README.md
git commit -F- <<'MSG'
docs: document discovery, its limits and the mDNS deployment trade-off

The important part is the honest one: the range scan works in the default
bridge-network container, mDNS does not and cannot, because multicast does
not cross the bridge. The host-network variant that makes mDNS work is
written down together with what it costs, rather than being recommended
outright.

Device Discovery leaves the Areas for Improvement list in contributing.md,
where it has sat since the beginning.
MSG
```

---

## Self-Review

**Spec coverage:** every section of the design maps to a task — core module (1–3), the `kind` deadlock (4), API and policy (5), `already_configured` (5, step 4), frontend and honesty rules (6), tests including the ungmocked core path (2, 4, 5, 7), docs (8). The `zeroconf>=0.149.12` floor appears in the global constraints and in Task 3.

**Placeholders:** none — every code step carries the actual code, every test step the actual assertions.

**Type consistency:** the finding dict keys (`ip`, `hostname`, `friendly_name`, `module`, `firmware_version`, `mac`, `requires_auth`) are identical across `parse_status`, `probe_host`, `service_info_to_finding`, the API's `already_configured` enrichment, and the frontend template. `create_discovery_job(method, hosts, *, runner, clock, background)` is called with the same signature in Tasks 4 and 5. `on_progress(completed, total)` matches between `scan_network`, `_run_discovery` and the job fields the frontend polls.

**Known soft spots, flagged rather than hidden:** Task 6 assumes the editor component exposes `devices` and `isDirty`, and Task 7 assumes an `app_server` fixture yielding a base URL. Both steps say to verify the real names first.
