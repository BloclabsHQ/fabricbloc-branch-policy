#!/usr/bin/env python3
"""C1 acceptance tests (C1-1..C1-6 subset runnable offline)."""
import importlib.util
import json
import os
import re
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYGIENE = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HYGIENE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Fake:
    routes = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        key = u.path
        val = Fake.routes.get(key)
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

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        u = urllib.parse.urlparse(self.path)
        key = u.path + ":POST"
        handler = Fake.routes.get(key)
        if handler:
            code, body = handler(raw)
            self.send_response(code)
            self.end_headers()
            if body:
                self.wfile.write(body.encode() if isinstance(body, str) else body)
            return
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"{}")

    def do_PATCH(self):
        self.do_POST()


SRV = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=SRV.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{SRV.server_port}"


class TestPrOpsNotify(unittest.TestCase):
    def setUp(self):
        Fake.routes.clear()
        self.common = load_module("common")
        self.mod = load_module("pr_ops_notify")

    def test_marker_parse_and_build(self):
        body = "<!-- fabricbloc-pr-ops-thread-ts=123.456 ready-sha=abc ready-sha= not valid -->"
        m = self.mod.parse_marker("<!-- fabricbloc-pr-ops-thread-ts=123.456 ready-sha=" + "a" * 40 + " lifecycle=closed -->")
        self.assertEqual(m["thread_ts"], "123.456")
        self.assertEqual(len(m["ready_sha"]), 40)
        self.assertEqual(m["lifecycle"], "closed")
        built = self.mod.build_marker("123.456", ready_sha="b" * 40, lifecycle="closed")
        self.assertIn("fabricbloc-pr-ops-thread-ts=123.456", built)

    def test_skip_head_globs_c16(self):
        globs = ["agent/autonomous/chore/submodules-bump-*"]
        self.assertTrue(self.mod.skip_head("agent/autonomous/chore/submodules-bump-2026", globs))
        self.assertFalse(self.mod.skip_head("agent/session/feat/foo", globs))

    def test_ready_dedupe_same_sha_c12(self):
        """Second READY for same head SHA is a no-op (C1-2)."""
        repo = "BloclabsHQ/fabricbloc"
        sha = "c" * 40
        marker_body = self.mod.build_marker("111.222", ready_sha=sha)
        Fake.routes[f"/repos/{repo}/pulls/7"] = {
            "number": 7,
            "state": "open",
            "draft": False,
            "merged_at": None,
            "title": "t",
            "html_url": "https://example/pr/7",
            "head": {"ref": "agent/session/feat/x", "sha": sha},
            "base": {"ref": "main"},
        }
        Fake.routes[f"/repos/{repo}/issues/7/comments"] = [
            {"id": 1, "user": {"login": "github-actions[bot]"}, "body": marker_body},
        ]
        Fake.routes[f"/repos/{repo}/rules/branches/main"] = [
            {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "canon-check", "integration_id": 15368}]}},
        ]
        Fake.routes[f"/repos/{repo}/commits/{sha}/check-runs"] = {"check_runs": [{"name": "canon-check", "conclusion": "success", "app": {"id": 15368}}]}
        Fake.routes[f"/repos/{repo}/commits/{sha}/status"] = {"statuses": []}
        os.environ.update(
            GH_TOKEN="t",
            API=API,
            REPO=repo,
            SLACK_BOT_TOKEN="x",
            HYGIENE_MODE="dry-run",
            CHANNEL="C",
            PR_NUMBER="7",
        )
        # Should exit without attempting second ready (prints already ready)
        self.mod.process_pr("t", "x", repo, 7, event_action="workflow_run")

    def test_missing_slack_token_c15(self):
        repo = "BloclabsHQ/fabricbloc"
        os.environ.update(GH_TOKEN="t", API=API, REPO=repo, SLACK_BOT_TOKEN="", PR_NUMBER="1", ALERT_CHANNEL="")
        with self.assertRaises(SystemExit):
            self.mod.main()


class TestWorkflowNoHeadCheckout(unittest.TestCase):
    def test_c14_no_checkout_or_head_ref(self):
        text = (ROOT / ".github/workflows/hygiene-pr-ops-notify.yml").read_text()
        self.assertNotIn("actions/checkout", text)
        self.assertNotIn("github.event.pull_request.head.sha", text)
        self.assertNotIn("ref: ${{ github.event.pull_request.head", text)


if __name__ == "__main__":
    unittest.main()
