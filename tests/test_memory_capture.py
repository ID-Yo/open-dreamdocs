import copy
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import automation_contract as ac
import memory_capture as mc
import project_memory as pm

CLI = [sys.executable, "-B", str(ROOT / "scripts/dreamdocs.py")]
EVENT = json.loads((ROOT / "tests/fixtures/automation/success-capture.json").read_text(encoding="utf-8"))["event"]
SECRET = "BEGIN PRIVATE KEY"


def event(**changes):
    value = copy.deepcopy(EVENT)
    outcome = changes.pop("outcome", {})
    value.update(changes)
    value["outcome"].update(outcome)
    return value


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="capture-test-")
        self.root = Path(self.temp.name).resolve()
        for name in (*pm.TYPES, "archive", "dreamer"):
            (self.root / "memory" / name).mkdir(parents=True)
            (self.root / "memory" / name / "README.md").write_text("# Folder\n", encoding="utf-8")
        (self.root / "memory/README.md").write_text("# Memory\n", encoding="utf-8")
        for name in ("automation", "automation/receipts", "dreamer/reports", "dreamer/proposals"):
            (self.root / "memory" / name).mkdir()
            shutil.copyfile(ROOT / "memory" / name / "README.md", self.root / "memory" / name / "README.md")
        (self.root / "memory/config.json").write_text(pm.canonical({"version": 1, "schedule": {"frequency": "daily", "timezone": None, "local_time": None, "owner": None}, "review": {"episode_days": None}}), encoding="utf-8")
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "example-project", "adapters": ["codex", "claude-code"]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def files(self, folder):
        path = self.root / folder
        return sorted(p.name for p in path.glob("*") if p.name != "README.md") if path.is_dir() else []

    def episodes(self):
        return self.files("memory/episodes")

    def receipt(self, value):
        return pm.read_json(self.root / "memory/automation/receipts" / f"{ac.event_id(value)}.json")

    def cli(self, value, *extra):
        path = self.root / "event.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return subprocess.run(CLI + ["--root", str(self.root), "memory", "capture", "--event", str(path), *extra], capture_output=True, text=True)

    def test_success_persists_episode_and_receipt_and_replay_is_duplicate(self):
        result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (0, "capture_episode", True))
        eid = ac.event_id(EVENT)
        episode = self.root / f"memory/episodes/auto-{eid}.md"
        meta = pm.metadata(episode.read_text(encoding="utf-8"))
        self.assertEqual((meta["id"], meta["type"], meta["status"], meta["project"], meta["created_at"]), (f"auto-{eid}", "episodic", "active", "example-project", EVENT["occurred_at"]))
        self.assertIn("ref:commit-abc123", meta["source"])
        self.assertIn("Run the focused test before the full suite.", episode.read_text(encoding="utf-8"))
        receipt = self.receipt(EVENT)
        self.assertEqual((receipt["status"], receipt["outcome"], receipt["episode"]), ("persisted", "success", f"memory/episodes/auto-{eid}.md"))
        self.assertEqual(receipt["episode_sha256"], pm.digest(episode.read_bytes()))
        before = episode.read_bytes(), (self.root / f"memory/automation/receipts/{eid}.json").read_bytes()
        replay = mc.capture(self.root, EVENT)
        self.assertEqual((replay["exit"], replay["decision"], replay["saved"]), (0, "duplicate", True))
        self.assertEqual(before, (episode.read_bytes(), (self.root / f"memory/automation/receipts/{eid}.json").read_bytes()))
        self.assertEqual(len(self.episodes()), 1)
        self.assertEqual(pm.validate(self.root)["records"], 1)

    def test_no_lesson_gets_bounded_receipt_only(self):
        value = event(outcome={"status": "no_lesson", "summary": "Routine answer.", "evidence": [], "lessons": []})
        result = mc.capture(self.root, value)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (0, "receipt_only", True))
        self.assertEqual(self.episodes(), [])
        receipt = self.receipt(value)
        self.assertEqual((receipt["status"], receipt["outcome"], receipt["episode"]), ("receipt_only", "no_lesson", None))
        self.assertLess(len(json.dumps(receipt)), 600)

    def test_failed_and_partial_outcomes_are_kept_as_such(self):
        for status in ("failed", "partial"):
            with self.subTest(status=status):
                value = event(turn_id=status, outcome={"status": status, "summary": f"Work {status}."})
                result = mc.capture(self.root, value)
                self.assertEqual((result["exit"], result["saved"]), (1, True))
                self.assertEqual(self.receipt(value)["outcome"], status)
                text = (self.root / f"memory/episodes/auto-{ac.event_id(value)}.md").read_text(encoding="utf-8")
                self.assertIn(f"Outcome: {status}", text)

    def test_crash_before_and_after_episode_write_recovers_once(self):
        with patch.object(mc, "atomic_text", side_effect=OSError(errno.EIO, "injected")):
            result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["saved"]), (2, False))
        self.assertEqual((self.episodes(), self.files("memory/automation/receipts")), ([], []))
        with patch.object(pm, "atomic", side_effect=OSError(errno.EIO, "injected")):
            result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["saved"]), (2, False))
        self.assertEqual((len(self.episodes()), self.files("memory/automation/receipts")), (1, []))
        result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (0, "capture_episode", True))
        self.assertEqual((len(self.episodes()), len(self.files("memory/automation/receipts"))), (1, 1))

    def test_retry_after_crash_and_source_edit_completes_the_receipt(self):
        (self.root / "docs").mkdir(exist_ok=True)
        (self.root / "docs/note.md").write_text("note v1\n", encoding="utf-8")
        value = event(outcome={"evidence": ["file:docs/note.md"]})
        with patch.object(pm, "atomic", side_effect=OSError(errno.EIO, "injected")):
            self.assertFalse(mc.capture(self.root, value)["saved"])
        episode = self.root / f"memory/episodes/auto-{ac.event_id(value)}.md"
        first = episode.read_bytes()
        (self.root / "docs/note.md").write_text("note v2\n", encoding="utf-8")
        result = mc.capture(self.root, value)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (0, "capture_episode", True))
        self.assertEqual(episode.read_bytes(), first)
        self.assertEqual(self.receipt(value)["episode_sha256"], pm.digest(first))
        self.assertEqual(mc.capture(self.root, value)["decision"], "duplicate")

    def test_retry_with_a_different_episode_body_is_still_a_conflict(self):
        value = event()
        with patch.object(pm, "atomic", side_effect=OSError(errno.EIO, "injected")):
            mc.capture(self.root, value)
        episode = self.root / f"memory/episodes/auto-{ac.event_id(value)}.md"
        episode.write_text(episode.read_text(encoding="utf-8").replace("Outcome: success", "Outcome: edited"), encoding="utf-8")
        self.assertEqual(mc.capture(self.root, value)["decision"], "conflict")


    def test_disk_full_and_permission_denied_never_report_saved(self):
        for error in (OSError(errno.ENOSPC, "No space left on device"), PermissionError(errno.EACCES, "Permission denied")):
            with self.subTest(error=error), patch.object(pm, "atomic", side_effect=error):
                result = mc.capture(self.root, event(turn_id=str(error.errno)))
                self.assertEqual((result["exit"], result["saved"]), (2, False))
                self.assertIn("not saved", result["findings"][0])
        self.assertEqual(self.files("memory/automation/receipts"), [])

    def test_same_identity_different_payload_is_conflict(self):
        mc.capture(self.root, EVENT)
        episode = (self.root / "memory/episodes").glob("auto-*.md").__next__()
        before = episode.read_bytes()
        result = mc.capture(self.root, event(outcome={"summary": "A different summary."}))
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (5, "conflict", False))
        self.assertEqual(before, episode.read_bytes())

    def test_reordered_events_each_persist(self):
        for turn in ("turn-2", "turn-1"):
            self.assertTrue(mc.capture(self.root, event(turn_id=turn))["saved"])
        self.assertEqual(len(self.episodes()), 2)
        self.assertEqual(pm.validate(self.root)["records"], 2)

    def test_unsafe_oversize_and_missing_source_are_rejected_without_copying(self):
        unsafe = event(turn_id="unsafe", outcome={"summary": f"Pasted -----{SECRET}----- marker."})
        run = self.cli(unsafe)
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertNotIn(SECRET, run.stdout + run.stderr)
        receipts = self.root / "memory/automation/receipts"
        self.assertFalse((receipts / f"{ac.event_id(unsafe)}.json").exists())
        oversize = event(turn_id="oversize", outcome={"summary": "x" * (ac.TEXT_LIMIT + 1)})
        self.assertEqual(mc.capture(self.root, oversize)["exit"], 2)
        self.assertEqual(self.episodes(), [])
        (self.root / "event.json").unlink()
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(encoding="utf-8", errors="replace"), path)
                self.assertNotIn("x" * 200, path.read_text(encoding="utf-8", errors="replace"), path)

    def hold_lock(self):
        lock = self.root / "memory/dreamer/command.lock"
        lock.write_text("live writer", encoding="utf-8")
        return lock

    def test_unverifiable_evidence_is_kept_as_ref_and_the_outcome_is_saved(self):
        refs = ["file:docs/missing.md", "file:C:/elsewhere/report.md", "file:../outside.md", "id:4490bf2eaa0556ad2011202f2839d4be05b8a722"]
        value = event(turn_id="unverifiable", outcome={"evidence": refs})
        result = mc.capture(self.root, value)
        self.assertEqual((result["exit"], result["saved"]), (0, True), result)
        text = (self.root / "memory/episodes" / f"auto-{ac.event_id(value)}.md").read_text(encoding="utf-8")
        meta = pm.metadata(text)
        self.assertEqual(meta["source"][:4], ["ref:" + ref for ref in refs])
        self.assertIn("Unverified evidence kept as ref: file:docs/missing.md (missing in this checkout)", text)
        self.assertIn("(outside this project)", text)
        self.assertIn("(not a memory record ID)", text)
        self.assertEqual(pm.validate_runtime(self.root)["records"], 1)
        self.assertEqual(mc.capture(self.root, value)["decision"], "duplicate")

    def test_deleting_a_cited_file_later_never_blocks_validation_or_new_captures(self):
        cited = self.root / "docs/report.md"
        cited.parent.mkdir(parents=True, exist_ok=True)
        cited.write_text("report\n", encoding="utf-8")
        first = event(turn_id="cites-report", outcome={"evidence": ["file:docs/report.md"]})
        self.assertTrue(mc.capture(self.root, first)["saved"])
        cited.unlink()
        self.assertTrue(mc.capture(self.root, event(turn_id="after-delete"))["saved"])
        self.assertIn(f"auto-{ac.event_id(first)}: cited file no longer present: docs/report.md", pm.validate(self.root)["warnings"])

    def test_missing_file_source_is_kept_as_ref_when_queued(self):
        lock = self.hold_lock()
        missing = event(outcome={"evidence": ["file:docs/missing.md"]})
        self.assertEqual(mc.capture(self.root, missing, budget=0)["decision"], "queued")
        lock.unlink()
        self.assertEqual(mc.reconcile(self.root)["published"], 1)
        meta = pm.metadata((self.root / "memory/episodes" / f"auto-{ac.event_id(missing)}.md").read_text(encoding="utf-8"))
        self.assertIn("ref:file:docs/missing.md", meta["source"])

    def test_refused_pending_entry_is_kept_and_reported_never_dropped(self):
        lock = self.hold_lock()
        unknown = event(turn_id="unknown-id")
        result = ac.check(unknown, pm.read_json(self.root / "memory/automation.json"))
        plan = mc.make_plan(self.root, unknown, result)
        plan["episode"] = plan["episode"].replace('"source": [', '"source": [\n    "id:no-such-record",', 1)
        mc.queue(self.root, plan)
        lock.unlink()
        other = mc.capture(self.root, event(turn_id="other"))
        self.assertTrue(other["saved"])
        self.assertEqual([(u["event_id"], u["decision"]) for u in other["unpublished"]], [(ac.event_id(unknown), "invalid")])
        reconciled = mc.reconcile(self.root)
        self.assertEqual((reconciled["exit"], reconciled["published"]), (2, 0))
        self.assertEqual([u["event_id"] for u in reconciled["unpublished"]], [ac.event_id(unknown)])
        self.assertEqual(self.files("memory/automation/pending"), [f"{ac.event_id(unknown)}.json"])
        self.assertFalse((self.root / "memory/automation/receipts" / f"{ac.event_id(unknown)}.json").exists())

    def test_same_identity_different_payload_in_queue_is_conflict(self):
        lock = self.hold_lock()
        rebuilt = event(occurred_at="2026-01-02T10:00:05Z")
        self.assertEqual(mc.capture(self.root, EVENT, budget=0)["decision"], "queued")
        pending = self.root / "memory/automation/pending" / f"{ac.event_id(EVENT)}.json"
        before = pending.read_bytes()
        busy = mc.capture(self.root, rebuilt, budget=0)
        self.assertEqual((busy["exit"], busy["decision"], busy["saved"]), (5, "conflict", False))
        self.assertEqual(before, pending.read_bytes())
        lock.unlink()
        free = mc.capture(self.root, rebuilt)
        self.assertEqual((free["exit"], free["decision"], free["saved"]), (5, "conflict", False))
        self.assertEqual(self.receipt(EVENT)["payload_sha256"], json.loads(before)["payload_sha256"])


    def test_receipt_decides_duplicate_and_conflict_without_the_lock(self):
        self.assertTrue(mc.capture(self.root, EVENT)["saved"])
        lock = self.hold_lock()
        started = time.monotonic()
        duplicate = mc.capture(self.root, EVENT)
        conflict = mc.capture(self.root, event(occurred_at="2026-01-02T10:00:05Z"))
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual((duplicate["exit"], duplicate["decision"], duplicate["saved"]), (0, "duplicate", True))
        self.assertEqual((conflict["exit"], conflict["decision"], conflict["saved"]), (5, "conflict", False))
        self.assertEqual(lock.read_text(encoding="utf-8"), "live writer")
        self.assertEqual(self.files("memory/automation/pending"), [])


    def test_malformed_pending_file_is_isolated_and_reported(self):
        bad = self.root / "memory/automation/pending/bad.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("not json", encoding="utf-8")
        result = mc.capture(self.root, EVENT)
        self.assertTrue(result["saved"])
        self.assertEqual([(u["pending"], u["decision"]) for u in result["unpublished"]], [("bad.json", "invalid")])
        reconciled = mc.reconcile(self.root)
        self.assertEqual((reconciled["exit"], [u["pending"] for u in reconciled["unpublished"]]), (2, ["bad.json"]))
        self.assertTrue(bad.exists())


    def test_waiting_writers_report_their_real_outcome_when_another_writer_publishes_them(self):
        lock = self.hold_lock()
        values = [event(turn_id=f"failed-{i}", outcome={"status": "failed", "summary": f"Attempt {i} failed.", "lessons": []}) for i in range(6)]
        processes = []
        for i, value in enumerate(values):
            path = self.root / f"failed-{i}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            processes.append(subprocess.Popen(CLI + ["--root", str(self.root), "memory", "capture", "--event", str(path), "--budget-ms", "20000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 15
        while len(self.files("memory/automation/pending")) < len(values) and time.monotonic() < deadline:
            time.sleep(0.05)
        lock.unlink()
        for process in processes:
            out, err = process.communicate(timeout=60)
            result = json.loads(out)
            self.assertEqual((process.returncode, result["decision"], result["saved"]), (1, "capture_episode", True), {"result": result, "stderr": err})
        self.assertEqual(len(self.episodes()), 6)


    def test_racing_queue_writers_with_different_payloads_yield_one_queued_and_one_conflict(self):
        self.hold_lock()
        for round_ in range(5):
            variants = [event(turn_id=f"race-{round_}", outcome={"summary": f"Variant {v}."}) for v in "ab"]
            processes = []
            for v, value in zip("ab", variants):
                path = self.root / f"race-{round_}-{v}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                processes.append(subprocess.Popen(CLI + ["--root", str(self.root), "memory", "capture", "--event", str(path), "--budget-ms", "0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            results = [json.loads(p.communicate(timeout=60)[0]) for p in processes]
            self.assertEqual(sorted(r["decision"] for r in results), ["conflict", "queued"], results)
            winner = variants[[r["decision"] for r in results].index("queued")]
            pending = pm.read_json(self.root / "memory/automation/pending" / f"{ac.event_id(winner)}.json")
            self.assertEqual(pending["payload_sha256"], ac.check(winner, None)["payload_sha256"])


    def test_queue_drains_in_arrival_order_so_later_captures_can_cite_earlier_ones(self):
        lock = self.hold_lock()
        first = event(turn_id="first")
        later = next(event(turn_id=f"later-{n}") for n in range(100) if ac.event_id(event(turn_id=f"later-{n}")) < ac.event_id(first))
        later["outcome"]["evidence"] = [f"id:auto-{ac.event_id(first)}"]
        self.assertEqual(mc.capture(self.root, first, budget=0)["decision"], "queued")
        time.sleep(0.05)
        self.assertEqual(mc.capture(self.root, later, budget=0)["decision"], "queued")
        lock.unlink()
        reconciled = mc.reconcile(self.root)
        self.assertEqual((reconciled["exit"], reconciled["published"], reconciled["unpublished"]), (0, 2, []))


    def test_missing_binding_writes_nothing(self):
        (self.root / "memory/automation.json").unlink()
        result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (4, "degraded", False))
        self.assertEqual((self.episodes(), self.files("memory/automation/receipts"), self.files("memory/automation/pending")), ([], [], []))

    def test_writer_creates_missing_folder_readmes(self):
        shutil.rmtree(self.root / "memory/automation/receipts")
        self.assertTrue(mc.capture(self.root, EVENT)["saved"])
        self.assertTrue((self.root / "memory/automation/receipts/README.md").is_file())
        self.assertTrue(pm.validate(self.root)["ok"])
        for folder, text in mc.READMES.items():
            self.assertEqual(text, (ROOT / folder / "README.md").read_text(encoding="utf-8"), folder)

    def test_dreamer_run_queues_capture_and_reconcile_publishes_after_release(self):
        run = pm.begin(self.root)
        result = mc.capture(self.root, EVENT)
        self.assertEqual((result["exit"], result["decision"], result["saved"]), (1, "queued", False))
        self.assertEqual((self.episodes(), len(self.files("memory/automation/pending"))), ([], 1))
        self.assertTrue((self.root / "memory/dreamer/lock.json").exists())
        pm.abort(self.root, run["run_id"])
        reconciled = mc.reconcile(self.root)
        self.assertEqual((reconciled["exit"], reconciled["published"]), (0, 1))
        self.assertEqual((len(self.episodes()), self.files("memory/automation/pending")), (1, []))
        self.assertEqual(self.receipt(EVENT)["status"], "persisted")
        self.assertTrue(pm.validate(self.root)["ok"])

    def test_live_writer_lock_is_never_stolen_and_session_end_budget_holds(self):
        lock = self.root / "memory/dreamer/command.lock"
        lock.write_text("live writer", encoding="utf-8")
        started = time.monotonic()
        run = self.cli(EVENT)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertEqual(json.loads(run.stdout)["decision"], "queued")
        self.assertEqual(lock.read_text(encoding="utf-8"), "live writer")
        lock.unlink()
        reconciled = subprocess.run(CLI + ["--root", str(self.root), "memory", "reconcile"], capture_output=True, text=True)
        self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
        self.assertEqual(len(self.episodes()), 1)

    def test_concurrent_writer_processes_lose_nothing_and_duplicate_nothing(self):
        values = [event(turn_id=f"turn-{i}") for i in range(6)] + [event(turn_id="turn-0"), event(turn_id="turn-1")]
        processes = []
        for i, value in enumerate(values):
            path = self.root / f"event-{i}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            processes.append(subprocess.Popen(CLI + ["--root", str(self.root), "memory", "capture", "--event", str(path), "--budget-ms", "10000"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        for process in processes:
            out, err = process.communicate(timeout=60)
            self.assertIn(process.returncode, (0, 1), err)
        mc.reconcile(self.root)
        self.assertEqual(len(self.episodes()), 6)
        self.assertEqual(len(self.files("memory/automation/receipts")), 6)
        self.assertEqual(self.files("memory/automation/pending"), [])
        self.assertFalse((self.root / "memory/dreamer/command.lock").exists())
        self.assertEqual(pm.validate(self.root)["records"], 6)


if __name__ == "__main__":
    unittest.main()

