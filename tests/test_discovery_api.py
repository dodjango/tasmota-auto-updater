"""Contract tests for the discovery endpoints."""
import pytest
from marshmallow import ValidationError

from app.tasmota import api, jobs
from server import create_app

MAX_PREFIX = 22


@pytest.fixture(autouse=True)
def _clean_jobs():
    jobs._reset_for_tests()
    yield
    jobs._reset_for_tests()


@pytest.fixture
def client():
    app = create_app()
    app.config.update({"TESTING": True})
    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session["ui_authenticated"] = True
        yield test_client


@pytest.mark.parametrize("value", [
    "192.168.1.0/24", "10.0.0.0/24", "172.16.4.0/23", "192.168.0.0/22",
])
def test_private_networks_within_the_limit_are_accepted(value):
    assert str(api.validate_scan_target(value)) == value


def test_a_host_address_is_normalised_to_its_network():
    """Typing your own address with a prefix must mean 'this network'.

    Nobody looks up their network address before scanning — they read the IP
    off a device. strict=False turns that into the range they meant.
    """
    assert str(api.validate_scan_target("192.168.1.55/24")) == "192.168.1.0/24"


def test_whitespace_around_the_network_is_tolerated():
    """Copy-paste from a router page brings whitespace along."""
    assert str(api.validate_scan_target("  10.0.0.0/24  ")) == "10.0.0.0/24"


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


def test_post_scan_passes_the_expanded_host_list(client, monkeypatch):
    """The API expands the CIDR; the core never sees a network object."""
    captured = {}

    def fake_job(method, hosts, **kwargs):
        captured["method"] = method
        captured["hosts"] = hosts
        return "job-x"

    monkeypatch.setattr(jobs, "create_discovery_job", fake_job)
    client.post("/api/discovery", json={"method": "scan", "network": "192.168.1.0/29"})
    assert captured["method"] == "scan"
    assert captured["hosts"] == [f"192.168.1.{n}" for n in range(1, 7)]


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


def test_findings_are_flagged_against_the_configured_devices(client, tmp_path):
    """A device already in the file must not be offered for adoption again."""
    devices_file = tmp_path / "devices.yaml"
    devices_file.write_text("devices:\n  - ip: 192.168.1.10\n")

    job_id = jobs.create_discovery_job(
        "scan", ["192.168.1.10", "192.168.1.11"],
        runner=lambda on_progress: [
            {"ip": "192.168.1.10", "requires_auth": False},
            {"ip": "192.168.1.11", "requires_auth": False},
        ],
        background=False,
    )

    app = create_app()
    app.config.update({"TESTING": True, "DEVICES_FILE": str(devices_file)})
    with app.test_client() as authed:
        with authed.session_transaction() as session:
            session["ui_authenticated"] = True
        body = authed.get(f"/api/jobs/{job_id}").get_json()

    flags = {entry["ip"]: entry["already_configured"] for entry in body["results"]}
    assert flags == {"192.168.1.10": True, "192.168.1.11": False}


def test_batch_job_results_are_left_alone(client):
    """The enrichment is discovery-only; a batch result must not grow a flag."""
    job_id = jobs.create_batch_job(
        [{"ip": "192.0.2.9"}], check_only=True, update_only_needed=False,
        global_timeout=None,
        updater=lambda cfg, check_only=False: {"success": True, "ip": cfg["ip"]},
        background=False,
    )
    body = client.get(f"/api/jobs/{job_id}").get_json()
    assert "already_configured" not in body["results"][0]
