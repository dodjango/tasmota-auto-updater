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
import time
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


# Tasmota announces itself over the generic HTTP service; some builds add a
# dedicated one. Browsing both costs nothing and catches both.
MDNS_SERVICES = ("_http._tcp.local.", "_tasmota._tcp.local.")

# How long to listen before answering. mDNS is passive — the only way to find
# more devices is to wait longer, and four seconds catches a home network.
MDNS_DURATION = 4.0


class MdnsUnavailable(RuntimeError):
    """zeroconf is not installed or could not be started."""


def _import_zeroconf():
    """Import zeroconf lazily so a missing package fails only the mDNS path.

    Separated into its own function so a test can replace it — the scan path
    must stay usable even where mDNS cannot work at all.
    """
    try:
        import zeroconf
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


def browse_mdns(duration: float = MDNS_DURATION) -> list[dict[str, Any]]:
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

    def _on_change(zeroconf_instance, service_type, name, state_change, **kwargs):
        if state_change is not module.ServiceStateChange.Added:
            return
        info = zeroconf_instance.get_service_info(service_type, name, timeout=1000)
        if info is None:
            return
        entry = service_info_to_finding(info)
        if entry:
            found.setdefault(entry["ip"], entry)

    try:
        instance = module.Zeroconf()
    except OSError as exc:
        # No multicast-capable interface, or the socket could not be bound.
        raise MdnsUnavailable(f"mDNS could not be started: {exc}") from exc

    try:
        browser = module.ServiceBrowser(instance, list(MDNS_SERVICES), handlers=[_on_change])
        time.sleep(duration)
        browser.cancel()
    finally:
        instance.close()

    return list(found.values())
