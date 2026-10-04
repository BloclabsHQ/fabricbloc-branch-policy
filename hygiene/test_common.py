#!/usr/bin/env python3
"""Shared hygiene helpers (manifest fail-closed)."""
import importlib.util
import json
import os
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HYGIENE = Path(__file__).resolve().parent


def load_common():
    spec = importlib.util.spec_from_file_location("common", HYGIENE / "common.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["common"] = mod
    spec.loader.exec_module(mod)
    return mod


class Fake:
    routes = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        val = Fake.routes.get(u.path)
        if isinstance(val, int):
            self.send_response(val)
            self.end_headers()
            return
        if val is None:
            self.send_response(404)
            self.end_headers()
            return
        body = val if isinstance(val, str) else json.dumps(val)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())


SRV = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{SRV.server_port}"
REPO = "BloclabsHQ/fabricbloc"
REF = "main"


class TestManifestFailClosed(unittest.TestCase):
    def setUp(self):
        Fake.routes.clear()
        self.common = load_common()
        os.environ["API"] = API
        os.environ["GH_TOKEN"] = "t"

    def _manifest_path(self):
        from urllib.parse import quote
        enc = quote("agents/runtime/engine/policy/cursor-env/manifest.json", safe="")
        return f"/repos/{REPO}/contents/{enc}"

    def test_missing_manifest_fails(self):
        Fake.routes[self._manifest_path() + f"?ref={REF}"] = 404
        with self.assertRaises(SystemExit):
            self.common.fetch_manifest_denied(REPO, REF, mode="test-manifest")

    def test_invalid_json_fails(self):
        Fake.routes[self._manifest_path() + f"?ref={REF}"] = "{not-json"
        with self.assertRaises(SystemExit):
            self.common.fetch_manifest_denied(REPO, REF, mode="test-manifest")

    def test_valid_manifest_ok(self):
        body = json.dumps({"denied_paths": {"arch_0048_baseline": [".github/workflows/"]}})
        Fake.routes[self._manifest_path() + f"?ref={REF}"] = body
        denied, never = self.common.fetch_manifest_denied(REPO, REF, mode="test-manifest")
        self.assertIn(".github/workflows/", denied)


if __name__ == "__main__":
    unittest.main()
