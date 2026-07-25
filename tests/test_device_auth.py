"""Tests for device authentication handling.

Credentials used to be embedded in the request URL (`http://user:pass@ip/cm`).
They are now passed via the request's `auth` argument instead, which produces the
same Authorization header while keeping the password out of the URL string — so it
cannot leak through logs, exception messages or `response.url`, and characters like
`:` or `@` in a password can no longer corrupt the URL.
"""

import requests

from app.tasmota.updater import build_device_auth, build_device_url

DEVICE = {"ip": "192.168.8.191", "username": "admin", "password": "s3cr3t"}


class TestBuildDeviceUrl:
    def test_url_carries_no_credentials(self):
        url = build_device_url(DEVICE)

        assert url == "http://192.168.8.191/cm"
        assert "s3cr3t" not in url
        assert "admin" not in url

    def test_accepts_a_plain_ip_string(self):
        assert build_device_url("192.168.8.191") == "http://192.168.8.191/cm"

    def test_honours_a_custom_path(self):
        assert build_device_url(DEVICE, path="status") == "http://192.168.8.191/status"

    def test_rejects_an_invalid_address(self):
        assert build_device_url({"ip": "not-an-ip"}) is None


class TestBuildDeviceAuth:
    def test_returns_the_credential_pair(self):
        assert build_device_auth(DEVICE) == ("admin", "s3cr3t")

    def test_returns_none_without_credentials(self):
        assert build_device_auth({"ip": "192.168.8.191"}) is None

    def test_returns_none_when_only_one_half_is_set(self):
        assert build_device_auth({"ip": "192.168.8.191", "username": "admin"}) is None
        assert build_device_auth({"ip": "192.168.8.191", "password": "s3cr3t"}) is None

    def test_returns_none_for_a_plain_ip_string(self):
        assert build_device_auth("192.168.8.191") is None


class TestWireEquivalence:
    """The request on the wire must be unchanged by moving credentials out of the URL."""

    def _prepared_authorization(self, url, auth):
        return requests.Request("GET", url, auth=auth).prepare().headers.get("Authorization")

    def test_auth_argument_matches_the_previous_userinfo_url(self):
        legacy = self._prepared_authorization("http://admin:s3cr3t@192.168.8.191/cm", None)
        current = self._prepared_authorization(build_device_url(DEVICE), build_device_auth(DEVICE))

        assert current == legacy
        assert current.startswith("Basic ")

    def test_passwords_with_url_metacharacters_now_survive(self):
        """A password containing ':' or '@' used to corrupt the embedded URL."""
        device = {"ip": "192.168.8.191", "username": "admin", "password": "p@ss:word"}

        prepared = requests.Request(
            "GET", build_device_url(device), auth=build_device_auth(device)
        ).prepare()

        assert prepared.url.startswith("http://192.168.8.191/cm")
        assert "p@ss:word" not in prepared.url
        # Decodes back to the exact credentials the device expects
        import base64
        token = prepared.headers["Authorization"].split(" ", 1)[1]
        assert base64.b64decode(token).decode() == "admin:p@ss:word"

    def test_no_authorization_header_without_credentials(self):
        device = {"ip": "192.168.8.191"}
        prepared = requests.Request(
            "GET", build_device_url(device), auth=build_device_auth(device)
        ).prepare()

        assert "Authorization" not in prepared.headers
