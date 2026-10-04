#!/usr/bin/env python3
"""C5 fixture tests."""
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


def load(name):
    spec = importlib.util.spec_from_file_location(name, HYGIENE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
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
        if val is None:
            self.send_response(404)
            self.end_headers()
            return
        body = val if isinstance(val, str) else json.dumps(val)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_DELETE(self):
        u = urllib.parse.urlparse(self.path)
        Fake.routes[u.path + ":DEL"] = True
        self.send_response(204)
        self.end_headers()


SRV = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{SRV.server_port}"
REPO = "BloclabsHQ/fabricbloc"


class TestBranchPrune(unittest.TestCase):
    def setUp(self):
        Fake.routes.clear()
        load("common")
        self.mod = load("branch_prune")

    def test_live_refused_without_ack_c53(self):
        os.environ.update(
            GH_TOKEN="t",
            API=API,
            REPO=REPO,
            HYGIENE_MODE="live",
            HYGIENE_C5_DRYRUN_ACK="",
            GITHUB_RUN_ID="run1",
        )
        Fake.routes[f"/repos/{REPO}"] = {"delete_branch_on_merge": True}
        with self.assertRaises(SystemExit):
            self.mod.main()

    def test_merged_proof_required_c54(self):
        branch = "agent/session/feat/old"
        sha = "a" * 40
        Fake.routes[f"/repos/{REPO}"] = {"delete_branch_on_merge": True}
        Fake.routes[f"/repos/{REPO}/git/matching-refs/heads/agent/"] = [
            {"ref": f"refs/heads/{branch}"},
        ]
        Fake.routes[f"/repos/{REPO}/pulls"] = []
        Fake.routes[f"/repos/{REPO}/branches/{branch}"] = {"protected": False}
        Fake.routes[f"/repos/{REPO}/rules/branches/{branch}"] = []
        Fake.routes[f"/repos/{REPO}/git/ref/heads/{branch}"] = {"object": {"sha": sha}}
        Fake.routes[f"/repos/{REPO}/commits/{sha}"] = {
            "commit": {"author": {"date": "2020-01-01T00:00:00Z"}},
        }
        Fake.routes[f"/repos/{REPO}/commits/{sha}/pulls"] = []
        os.environ.update(
            GH_TOKEN="t",
            API=API,
            REPO=REPO,
            HYGIENE_MODE="dry-run",
            GITHUB_RUN_ID="run1",
            SLACK_BOT_TOKEN="",
        )
        self.mod.main()


if __name__ == "__main__":
    unittest.main()
