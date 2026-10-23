import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
import memory_capture as mc
import project_memory as pm
import memory_health as mh

EVENT = json.loads((ROOT / "tests/fixtures/automation/success-capture.json").read_text(encoding="utf-8"))["event"]


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="memory-health-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        self.addCleanup(patch.stopall)
        patch.object(install, "codex_version", return_value="0.147.0").start()
        install.setup(self.root, True, "example-project")

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def codes(self, report):
        return {f["code"] for f in report["findings"]}

    def test_receipt_readback_never_proves_hook_trust_or_recall_and_default_is_read_only(self):
        mc.capture(self.root, copy.deepcopy(EVENT))
        before = self.snapshot()
        result = mh.doctor(self.root)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(result["capture"]["readback"], "verified")
        self.assertEqual(result["clients"]["codex"]["trust"], "unknown")
        self.assertEqual(result["clients"]["codex"]["recall"], "unknown")
        self.assertNotEqual(result["exit"], 0)

    def test_locks_queues_leftovers_and_schema_are_actionable_and_never_removed(self):
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        lock = self.root / "memory/dreamer/command.lock"
        pm.atomic(lock, {"owner_pid": 99999999, "acquired_at": old})
        pending = self.root / "memory/automation/pending/broken.json"
        pending.parent.mkdir(parents=True)
        pending.write_text("null", encoding="utf-8")
        events = self.root / "memory/automation/events/broken.json"
        events.parent.mkdir(parents=True)
        events.write_text("{}", encoding="utf-8")
        result = mh.doctor(self.root, fix=True)
        self.assertTrue({"aged_lock", "malformed_pending", "leftover_event"} <= self.codes(result))
        self.assertTrue(lock.exists() and pending.exists() and events.exists())

    def test_changed_missing_duplicate_hook_version_and_readback_are_separate(self):
        mc.capture(self.root, copy.deepcopy(EVENT))
        receipt = next((self.root / "memory/automation/receipts").glob("*.json"))
        episode = pm.read_json(receipt)["episode"]
        (self.root / episode).write_text("changed", encoding="utf-8")
        hook = self.root / ".codex/hooks.json"
        data = pm.read_json(hook)
        data["hooks"]["Stop"] *= 2
        pm.atomic(hook, data)
        with patch.object(install, "codex_version", return_value="new-version"):
            result = mh.doctor(self.root)
        self.assertTrue({"hook_changed", "client_version_changed", "readback_mismatch"} <= self.codes(result))
        hook.unlink()
        self.assertIn("hook_missing", self.codes(mh.doctor(self.root)))

    def test_smoke_is_isolated_and_saves_then_retrieves_a_unique_value(self):
        before = self.snapshot()
        result = mh.doctor(self.root, smoke=True)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(result["smoke"]["saved"] and result["smoke"]["retrieved"])
        self.assertEqual(result["smoke"]["scope"], "isolated local engine only")
        self.assertEqual(result["clients"]["codex"]["trust"], "unknown")

    def test_explicit_evidence_is_checked_against_config_source_and_observation_time(self):
        record = pm.read_json(self.root / install.MANIFEST)["clients"]["codex"]
        source = self.root / "observed.txt"
        source.write_text("Human observed the actual client trust screen.", encoding="utf-8")
        evidence = {"version": 1, "clients": {"codex": {"trust": {
            "kind": "client-trust", "observed_at": pm.now(), "client_version": record["version"],
            "command_sha256": record["command_sha256"], "source": "observed.txt",
            "sha256": pm.digest(source.read_bytes())}}}}
        result = mh.doctor(self.root, fix=True, evidence=evidence)
        self.assertEqual(result["clients"]["codex"]["trust"], "reported_trusted")
        self.assertEqual(result["clients"]["codex"]["recall"], "unknown")
        manifest = pm.read_json(self.root / install.MANIFEST)
        self.assertEqual(manifest["clients"]["codex"]["trust"], "trusted")
        import test_install_schema
        schema = pm.read_json(self.root / "templates/install-manifest.schema.json")
        test_install_schema.shape(manifest, schema)
        source.write_text("edited", encoding="utf-8")
        self.assertEqual(mh.doctor(self.root)["clients"]["codex"]["trust"], "unknown")

    def test_missing_task_receipt_is_reported_without_resuming_paused_tasks(self):
        event = copy.deepcopy(EVENT)
        event["task"] = {"id": "task-1", "status": "done"}
        result = mh.doctor(self.root, checkpoints=[{"task_id": "task-1", "event": event, "status": "done", "expected_at": "2020-01-01T00:00:00Z"},
                                                  {"task_id": "paused", "event_id": None, "status": "paused", "expected_at": None}])
        self.assertIn("missing_save", self.codes(result))
        self.assertEqual([f["scope"] for f in result["findings"] if f["code"] == "missing_save"], ["task-1"])

    def test_malformed_manifest_shapes_report_findings_without_tracebacks(self):
        original = pm.read_json(self.root / install.MANIFEST)
        for changed in ([], None, {**original, "package": []}, {**original, "clients": []},
                        {**original, "clients": {"codex": {"health": []}}}, {**original, "package_files": []}):
            pm.atomic(self.root / install.MANIFEST, changed)
            before = self.snapshot()
            result = mh.doctor(self.root, fix=True)
            self.assertNotEqual(result["exit"], 0)
            self.assertIn("invalid_manifest", self.codes(result))
            self.assertEqual(before, self.snapshot())

    def test_receipt_for_another_task_or_payload_cannot_satisfy_checkpoint(self):
        event = copy.deepcopy(EVENT)
        mc.capture(self.root, event)
        expected = copy.deepcopy(event)
        expected["task"] = {"id": "other-task", "status": "done"}
        result = mh.doctor(self.root, checkpoints=[{"task_id": "other-task", "event": expected, "status": "done", "expected_at": pm.now()}])
        self.assertIn("missing_save", self.codes(result))
        result = mh.doctor(self.root, checkpoints=[{"task_id": "other-task", "event": event, "status": "done", "expected_at": pm.now()}])
        self.assertIn("invalid_checkpoint", self.codes(result))
        event["task"] = {"id": "real-task", "status": "done"}
        event["turn_id"] = "new-task-turn"
        mc.capture(self.root, event)
        result = mh.doctor(self.root, checkpoints=[{"task_id": "real-task", "event": event, "status": "done", "expected_at": pm.now()}])
        self.assertFalse({"missing_save", "invalid_checkpoint"} & self.codes(result))
        result = mh.doctor(self.root, checkpoints=[{"task_id": "not-due", "status": "done", "expected_at": "2099-01-01T00:00:00Z"}])
        self.assertFalse({"missing_save", "invalid_checkpoint"} & self.codes(result))

    def test_fix_refuses_manifest_changed_after_scan(self):
        original_operation = pm.operation
        from contextlib import contextmanager
        @contextmanager
        def change_before_lock(root):
            manifest = pm.read_json(root / install.MANIFEST)
            manifest["package"]["version"] = "concurrent-owner-edit"
            pm.atomic(root / install.MANIFEST, manifest)
            with original_operation(root):
                yield
        with patch.object(pm, "operation", side_effect=change_before_lock):
            result = mh.doctor(self.root, fix=True)
        self.assertIn("manifest_changed_during_scan", self.codes(result))
        self.assertEqual(pm.read_json(self.root / install.MANIFEST)["package"]["version"], "concurrent-owner-edit")
        self.assertFalse(result["applied"])

    def test_cli_smoke_is_machine_readable_and_does_not_mutate_the_project(self):
        import subprocess
        before = self.snapshot()
        run = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/dreamdocs.py"), "--root", str(self.root), "doctor", "--smoke"],
                             capture_output=True, timeout=30)
        result = json.loads(run.stdout.decode("ascii"))
        self.assertEqual(run.returncode, result["exit"])
        self.assertTrue(result["smoke"]["retrieved"])
        self.assertEqual(before, self.snapshot())

    def test_inconsistent_receipt_is_not_readback_or_duplicate_proof(self):
        event = copy.deepcopy(EVENT)
        mc.capture(self.root, event)
        path = mc.receipt_path(self.root, mh.ac.event_id(event))
        receipt = pm.read_json(path)
        receipt.update(status="receipt_only", episode="memory/episodes/nonexistent.md")
        pm.atomic(path, receipt)
        self.assertIn("readback_mismatch", self.codes(mh.doctor(self.root)))
        self.assertNotEqual(mh.doctor(self.root)["capture"]["readback"], "verified")
        self.assertEqual(mh.ac.check(event, pm.read_json(self.root / "memory/automation.json"), receipt)["decision"], "invalid")
        self.assertFalse(mc.capture(self.root, event)["saved"])

    def test_invalid_evidence_shapes_are_structured_and_never_written(self):
        for value in (None, [], {}, {"version": 1, "clients": []}, {"version": 1, "clients": None},
                      {"version": 1, "clients": {"codex": {"trust": {"unexpected": 1}}}},
                      {"version": 1, "clients": {"codex": []}}, {"version": 1, "clients": {"codex": {"trust": None}}}):
            before = self.snapshot()
            result = mh.doctor(self.root, fix=True, evidence=value)
            self.assertIn("invalid_evidence", self.codes(result))
            self.assertEqual(result["exit"], 2)
            self.assertFalse(result["applied"])
            self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
