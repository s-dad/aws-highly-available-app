"""Tests for SafeClick v0. Run with: python3 -m unittest discover tests"""
import base64
import gzip
import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

with mock.patch("urllib.request.OpenerDirector.open", side_effect=OSError("no metadata in tests")):
    import safeclick  # noqa: E402


class ResolveTargetTests(unittest.TestCase):
    """The scanner must refuse anything that isn't a public web address (SSRF protection)."""

    def assert_blocked(self, url):
        with self.assertRaises(safeclick.ScanError, msg=url):
            safeclick.resolve_target(url)

    def test_blocks_internal_addresses(self):
        for url in ["http://127.0.0.1", "localhost", "http://10.0.0.5", "192.168.1.1",
                    "http://169.254.169.254/latest/meta-data/", "172.16.0.10",
                    "http://0.0.0.0", "http://[::1]/", "100.64.0.1"]:
            self.assert_blocked(url)

    def test_blocks_other_schemes_and_ports(self):
        for url in ["ftp://example.com", "file:///etc/passwd", "gopher://example.com",
                    "https://example.com:8080", "https://example.com:22"]:
            self.assert_blocked(url)

    def test_blocks_empty_and_oversized(self):
        self.assert_blocked("")
        self.assert_blocked("   ")
        self.assert_blocked("https://example.com/" + "a" * 3000)

    def test_blocks_hostname_that_resolves_internal(self):
        fake = [(2, 1, 6, "", ("10.1.2.3", 443))]
        with mock.patch("socket.getaddrinfo", return_value=fake):
            self.assert_blocked("sneaky.example.com")

    def test_allows_public_address(self):
        fake = [(2, 1, 6, "", ("93.184.215.14", 443))]
        with mock.patch("socket.getaddrinfo", return_value=fake):
            host, ip = safeclick.resolve_target("Example.com/path")
        self.assertEqual((host, ip), ("example.com", "93.184.215.14"))


class HeaderTests(unittest.TestCase):
    def test_frame_ancestors_counts_as_frame_protection(self):
        results = safeclick.check_headers({"content-security-policy": "frame-ancestors 'none'"})
        by_name = {r["header"]: r["present"] for r in results}
        self.assertTrue(by_name["X-Frame-Options"])
        self.assertTrue(by_name["Content Security Policy"])
        self.assertFalse(by_name["HSTS"])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), safeclick.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def get(self, path):
        try:
            resp = self.opener.open(self.base + path, timeout=5)
            return resp.status, resp.headers, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.headers, err.read().decode()

    def test_health_returns_200(self):
        status, _, body = self.get("/health")
        self.assertEqual((status, body), (200, "ok"))

    def test_home_page_shows_instance_id_for_load_balancer_tests(self):
        # The lab's curl loop greps for "Instance ID", so it must be in the HTML itself.
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Instance ID:", body)
        self.assertIn("Availability Zone:", body)
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_scan_rejects_internal_target(self):
        status, _, body = self.get("/api/scan?url=http://169.254.169.254/")
        self.assertEqual(status, 400)
        self.assertIn("private or internal", json.loads(body)["error"])

    def test_unknown_path_is_404(self):
        status, _, _ = self.get("/nope")
        self.assertEqual(status, 404)


class UserDataTests(unittest.TestCase):
    def test_user_data_embeds_current_app(self):
        script = (ROOT / "infra" / "user-data.sh").read_text()
        self.assertLessEqual(len(script.encode()), 16 * 1024)
        blob = re.search(r"<<'SAFECLICK_APP'[^\n]*\n(.*?)\nSAFECLICK_APP", script, re.S).group(1)
        embedded = gzip.decompress(base64.b64decode(blob.replace("\n", "")))
        self.assertEqual(embedded, (ROOT / "app" / "safeclick.py").read_bytes(),
                         "infra/user-data.sh is stale: run python3 scripts/build_user_data.py")


if __name__ == "__main__":
    unittest.main()
