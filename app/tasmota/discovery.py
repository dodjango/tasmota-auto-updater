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

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

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
        payload = json.loads(text)
    except ValueError:
        return None

    return parse_status(payload, ip)


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
