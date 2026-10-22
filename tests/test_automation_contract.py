import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import automation_contract as ac

FIXTURES = ROOT / "tests" / "fixtures" / "automation"
REQUIRED = {"success-capture", "no-lesson", "failed-task", "partial-task", "interrupted", "unsafe-secret",
            "missing-runtime", "paused-task", "duplicate-delivery", "conflicting-delivery", "foreign-project"}


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def receipt_for(fixture):
    if "receipt" not in fixture:
        return None
    first = ac.check(fixture["event"], fixture["binding"])
    payload = first["payload_sha256"] if fixture["receipt"] == "same" else "0" * 64
    return {"version": 1, "event_id": first["event_id"], "payload_sha256": payload, "status": "persisted"}


class ContractFixtureTests(unittest.TestCase):
    def test_required_cases_exist(self):
        self.assertLessEqual(REQUIRED, {p.stem for p in FIXTURES.glob("*.json")})

    def test_every_fixture_matches_expected_decision(self):
        for path in sorted(FIXTURES.glob("*.json")):
            fixture = load(path.stem)
            with self.subTest(fixture=path.stem):
                result = ac.check(fixture["event"], fixture["binding"], receipt_for(fixture))
                self.assertEqual((result["exit"], result["decision"]), (fixture["expect"]["exit"], fixture["expect"]["decision"]), result["findings"])
                self.assertFalse(result["resume_authorized"])
                self.assertEqual(result["promotion"], "review-required")


class ContractRuleTests(unittest.TestCase):
    def setUp(self):
        fixture = load("success-capture")
        self.event, self.binding = fixture["event"], fixture["binding"]

    def test_identity_is_stable_and_scoped(self):
        first = ac.check(self.event, self.binding)
        reordered = json.loads(json.dumps(dict(reversed(list(self.event.items())))))
        self.assertEqual(first["event_id"], ac.check(reordered, self.binding)["event_id"])
        edited = {**self.event, "outcome": {**self.event["outcome"], "summary": "Different summary."}}
        second = ac.check(edited, self.binding)
        self.assertEqual(first["event_id"], second["event_id"])
        self.assertNotEqual(first["payload_sha256"], second["payload_sha256"])
        for key in ("adapter", "session_id", "turn_id", "project_id", "worktree", "agent", "kind"):
            changed = {**self.event, key: "claude-code" if key == "adapter" else "task_start" if key == "kind" else "other"}
            if key == "kind":
                changed["outcome"] = None
            self.assertNotEqual(first["event_id"], ac.event_id(changed), key)
        self.assertEqual(first["episode"], f"memory/episodes/auto-{first['event_id']}.md")
        self.assertEqual(first["receipt"], f"memory/automation/receipts/{first['event_id']}.json")

    def test_strict_schema_blocks_promotion_and_bulk_capture(self):
        cases = [
            {**self.event, "promote": True},
            {**self.event, "outcome": {**self.event["outcome"], "lessons": [{"text": "x", "status": "active"}]}},
            {**self.event, "outcome": {**self.event["outcome"], "summary": "x" * (ac.TEXT_LIMIT + 1)}},
            {**self.event, "outcome": {**self.event["outcome"], "lessons": ["x"] * (ac.MAX_LESSONS + 1)}},
            {**self.event, "outcome": {**self.event["outcome"], "evidence": []}},
            {**self.event, "outcome": {**self.event["outcome"], "evidence": ["C:/private/raw.log"]}},
            {**self.event, "occurred_at": "2026-01-02"},
            {**self.event, "version": 2},
            {**self.event, "kind": "session_start"},
        ]
        for event in cases:
            with self.subTest(event=event):
                result = ac.check(event, self.binding)
                self.assertEqual((result["exit"], result["decision"]), (2, "invalid"))

    def test_support_matrix_is_truthful_for_both_clients(self):
        self.assertEqual(set(ac.SUPPORT), {"codex", "claude-code"})
        for client, entry in ac.SUPPORT.items():
            with self.subTest(client=client):
                self.assertIn(entry["state"], {"unsupported", "unverified", "tested"})
                if entry["state"] == "tested":
                    self.assertTrue(all(entry.get(k) for k in ("client_version", "os", "surface", "tested_at", "evidence")))
        result = ac.check(self.event, self.binding)
        self.assertEqual(result["support"], ac.SUPPORT["codex"]["state"])
        self.assertFalse(result["automatic"])

    def test_cli_is_read_only_and_uses_exit_codes(self):
        with tempfile.TemporaryDirectory(prefix="contract-cli-") as folder:
            root = Path(folder)
            event = root / "event.json"
            event.write_text(json.dumps(self.event), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT / "scripts/automation_contract.py"), "--root", str(root), "--event", str(event)]
            missing = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 4, missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["decision"], "degraded")
            (root / "memory").mkdir()
            (root / "memory/automation.json").write_text(json.dumps(self.binding), encoding="utf-8")
            before = sorted(p.relative_to(root) for p in root.rglob("*"))
            ok = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(before, sorted(p.relative_to(root) for p in root.rglob("*")))
            event.write_text("{not json", encoding="utf-8")
            self.assertEqual(subprocess.run(command, capture_output=True, text=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()

