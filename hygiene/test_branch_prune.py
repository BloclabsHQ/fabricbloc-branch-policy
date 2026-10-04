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
POLICY_WORKFLOW = (
    "BloclabsHQ/fabricbloc-branch-policy/.github/workflows/hygiene-branch-prune.yml"
)


def policy_workflow_path(at_ref):
    return f"{POLICY_WORKFLOW}@{at_ref}"


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
        if isinstance(val, dict) and "__http_status__" in val:
            self.send_response(val["__http_status__"])
            self.end_headers()
            body = val.get("body", "")
            if body:
                self.wfile.write(body.encode() if isinstance(body, str) else body)
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
TOKEN = "t"


def good_ack_run(at_ref="024c3adb251c555f8793f7af08dc80a963ba56de"):
    return {
        "status": "completed",
        "conclusion": "success",
        "referenced_workflows": [{"path": policy_workflow_path(at_ref)}],
    }


class TestBranchPrune(unittest.TestCase):
    def setUp(self):
        Fake.routes.clear()
        sys.modules.pop("common", None)
        sys.modules.pop("branch_prune", None)
        os.environ["API"] = API
        load("common")
        self.mod = load("branch_prune")

    def test_live_refused_without_ack_c53(self):
        os.environ.update(
            GH_TOKEN=TOKEN,
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
            GH_TOKEN=TOKEN,
            API=API,
            REPO=REPO,
            HYGIENE_MODE="dry-run",
            GITHUB_RUN_ID="run1",
            SLACK_BOT_TOKEN="",
        )
        self.mod.main()


class TestParseAckRunId(unittest.TestCase):
    def setUp(self):
        sys.modules.pop("branch_prune", None)
        self.mod = load("branch_prune")

    def test_numeric_run_id(self):
        self.assertEqual(self.mod.parse_ack_run_id("12345678", REPO), "12345678")

    def test_github_actions_url(self):
        url = f"https://github.com/{REPO}/actions/runs/999"
        self.assertEqual(self.mod.parse_ack_run_id(url, REPO), "999")

    def test_malformed_ack(self):
        self.assertIsNone(self.mod.parse_ack_run_id("not-a-run", REPO))

    def test_url_wrong_repo_fails_closed(self):
        url = "https://github.com/OtherOrg/other-repo/actions/runs/999"
        with self.assertRaises(SystemExit):
            self.mod.parse_ack_run_id(url, REPO)


class TestVerifyDryrunAck(unittest.TestCase):
    def setUp(self):
        Fake.routes.clear()
        sys.modules.pop("common", None)
        sys.modules.pop("branch_prune", None)
        os.environ["API"] = API
        load("common")
        self.mod = load("branch_prune")

    def _run_route(self, run_id):
        return f"/repos/{REPO}/actions/runs/{run_id}"

    def test_accepts_valid_id_and_referenced_workflow(self):
        run_id = "88001"
        Fake.routes[self._run_route(run_id)] = good_ack_run()
        out = self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)
        self.assertEqual(out, run_id)

    def test_accepts_valid_url(self):
        run_id = "88002"
        Fake.routes[self._run_route(run_id)] = good_ack_run("024c3adb251c555f8793f7af08dc80a963ba56de")
        url = f"https://github.com/{REPO}/actions/runs/{run_id}"
        self.mod.verify_dryrun_ack(TOKEN, REPO, url)

    def test_accepts_branch_ref_in_full_path(self):
        run_id = "88012"
        Fake.routes[self._run_route(run_id)] = good_ack_run("refs/heads/main")
        self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_accepts_pin_sha_in_full_path(self):
        run_id = "88013"
        Fake.routes[self._run_route(run_id)] = good_ack_run(
            "024c3adb251c555f8793f7af08dc80a963ba56de"
        )
        self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_malformed_ack(self):
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, "garbage")

    def test_rejects_failed_conclusion(self):
        run_id = "88003"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "failure",
            "referenced_workflows": [{"path": policy_workflow_path("refs/heads/main")}],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_cancelled_conclusion(self):
        run_id = "88004"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "cancelled",
            "referenced_workflows": [{"path": policy_workflow_path("refs/heads/main")}],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_in_progress_status(self):
        run_id = "88005"
        Fake.routes[self._run_route(run_id)] = {
            "status": "in_progress",
            "conclusion": None,
            "referenced_workflows": [{"path": policy_workflow_path("refs/heads/main")}],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_bare_workflow_path(self):
        run_id = "88006"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [
                {"path": ".github/workflows/hygiene-branch-prune.yml"},
            ],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_evil_org_policy_workflow_path(self):
        run_id = "88014"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [
                {
                    "path": (
                        "evil/fabricbloc-branch-policy/.github/workflows/"
                        "hygiene-branch-prune.yml@deadbeef"
                    ),
                },
            ],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_bloclabs_wrong_workflow_file(self):
        run_id = "88015"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [
                {
                    "path": (
                        "BloclabsHQ/other/.github/workflows/hygiene-branch-prune.yml@main"
                    ),
                },
            ],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_wrong_referenced_workflow_path(self):
        run_id = "88016"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [
                {
                    "path": (
                        "BloclabsHQ/fabricbloc-branch-policy/.github/workflows/"
                        "other.yml@refs/heads/main"
                    ),
                },
            ],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_empty_referenced_workflow_path(self):
        run_id = "88007"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [{"path": ""}],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_rejects_missing_referenced_workflow_path(self):
        run_id = "88008"
        Fake.routes[self._run_route(run_id)] = {
            "status": "completed",
            "conclusion": "success",
            "referenced_workflows": [{}],
        }
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_api_error_fails_closed(self):
        run_id = "88010"
        Fake.routes[self._run_route(run_id)] = {"__http_status__": 403, "body": "nope"}
        with self.assertRaises(SystemExit):
            self.mod.verify_dryrun_ack(TOKEN, REPO, run_id)

    def test_live_main_with_valid_ack(self):
        run_id = "88011"
        branch = "agent/session/feat/old"
        sha = "c" * 40
        Fake.routes[self._run_route(run_id)] = good_ack_run()
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
            GH_TOKEN=TOKEN,
            API=API,
            REPO=REPO,
            HYGIENE_MODE="live",
            HYGIENE_C5_DRYRUN_ACK=run_id,
            GITHUB_RUN_ID="run-live",
            SLACK_BOT_TOKEN="",
        )
        self.mod.main()


if __name__ == "__main__":
    unittest.main()
