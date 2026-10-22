import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project_memory as pm


class MemoryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dreamer-test-")
        self.root = Path(self.temp.name).resolve()
        for name in (*pm.TYPES, "archive", "dreamer"):
            (self.root / "memory" / name).mkdir(parents=True)
        self.config = {"version": 1, "schedule": {"frequency": "daily", "timezone": None, "local_time": None, "owner": None}, "review": {"episode_days": None}}
        self.write_json("memory/config.json", self.config)
        self.meta = {"id": "ep-001", "type": "episodic", "status": "active", "project": "test", "scope": "build", "created_at": "2026-01-01T00:00:00Z", "source": ["ref:test-suite"], "pinned": False}
        self.write_record("memory/episodes/one.md", self.meta)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pm.canonical(data), encoding="utf-8")

    def write_record(self, name, meta, body="# Test record\nObserved result."):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + json.dumps(meta, indent=2) + "\n---\n\n" + body + "\n", encoding="utf-8")

    def prepare(self, run_id, status="success", proposals=None):
        folder = self.root / "memory/dreamer/work" / run_id
        snapshot = pm.read_json(folder / "snapshot.json")
        result = {"run_id": run_id, "status": status, "summary": "Reviewed synthetic inputs.", "reviewed_ids": [r["metadata"]["id"] for r in snapshot["records"]], "proposals": proposals or []}
        self.write_json(f"memory/dreamer/work/{run_id}/result.json", result)
        return result

    def proposal(self):
        return {"kind": "fact", "title": "Build evidence", "body": "Candidate from a synthetic episode.", "source_ids": ["ep-001"]}

    def test_first_run_success_then_empty_run(self):
        first = pm.begin(self.root)
        self.assertEqual(first["records"], 1)
        with self.assertRaises(pm.MemoryError):
            pm.finish(self.root, first["run_id"])
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())
        self.prepare(first["run_id"])
        self.assertTrue(pm.finish(self.root, first["run_id"])["checkpoint_advanced"])
        second = pm.begin(self.root)
        self.assertEqual(second["records"], 0)
        self.prepare(second["run_id"])
        pm.finish(self.root, second["run_id"])

    def test_templates_examples_archive_readmes_and_outputs_excluded(self):
        for name in ("templates/episode.md", "examples/fact.md", "memory/dreamer/reports/mock.md", "memory/episodes/README.md"):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("not a real record", encoding="utf-8")
        archived = {**self.meta, "id": "ep-old", "status": "archived"}
        self.write_record("memory/archive/old.md", archived)
        run = pm.begin(self.root)
        self.assertEqual(run["records"], 1)
        pm.abort(self.root, run["run_id"])

    def test_added_record_during_run_is_not_skipped(self):
        run = pm.begin(self.root)
        self.prepare(run["run_id"])
        self.write_record("memory/episodes/late.md", {**self.meta, "id": "ep-late"})
        with self.assertRaisesRegex(pm.MemoryError, "input changed"):
            pm.finish(self.root, run["run_id"])
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())
        pm.abort(self.root, run["run_id"])
        retry = pm.begin(self.root)
        self.assertEqual(retry["records"], 2)
        pm.abort(self.root, retry["run_id"])

    def test_changed_and_deleted_record_during_run_fail(self):
        for action in ("edit", "delete"):
            with self.subTest(action=action):
                self.write_record("memory/episodes/one.md", self.meta)
                run = pm.begin(self.root)
                self.prepare(run["run_id"])
                if action == "edit":
                    self.write_record("memory/episodes/one.md", self.meta, "changed")
                else:
                    (self.root / "memory/episodes/one.md").unlink()
                with self.assertRaises(pm.MemoryError):
                    pm.finish(self.root, run["run_id"])
                pm.abort(self.root, run["run_id"])
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())

    def test_partial_failed_do_not_advance_previous_checkpoint(self):
        first = pm.begin(self.root)
        self.prepare(first["run_id"])
        pm.finish(self.root, first["run_id"])
        checkpoint = (self.root / "memory/dreamer/state.json").read_bytes()
        for status in ("partial", "failed"):
            self.write_record("memory/episodes/one.md", self.meta, status)
            run = pm.begin(self.root)
            result = self.prepare(run["run_id"], status)
            result["reviewed_ids"] = []
            self.write_json(f"memory/dreamer/work/{run['run_id']}/result.json", result)
            self.assertFalse(pm.finish(self.root, run["run_id"])["checkpoint_advanced"])
            self.assertEqual(checkpoint, (self.root / "memory/dreamer/state.json").read_bytes())

    def test_concurrent_run_wrong_run_and_traversal_rejected(self):
        run = pm.begin(self.root)
        for call in (lambda: pm.begin(self.root), lambda: pm.finish(self.root, "../outside"), lambda: pm.abort(self.root, "wrong-run")):
            with self.assertRaises(pm.MemoryError):
                call()
        self.assertTrue((self.root / "memory/dreamer/lock.json").exists())
        pm.abort(self.root, run["run_id"])

    def test_snapshot_tamper_fails(self):
        run = pm.begin(self.root)
        snapshot = self.root / run["snapshot"]
        snapshot.write_text(snapshot.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(pm.MemoryError, "snapshot modified"):
            pm.finish(self.root, run["run_id"])

    def test_explicit_recovery_age_and_confirmation(self):
        run = pm.begin(self.root)
        with self.assertRaises(pm.MemoryError):
            pm.recover(self.root, run["run_id"], 60, True)
        lock_path = self.root / "memory/dreamer/lock.json"
        lock = pm.read_json(lock_path)
        lock["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.write_json("memory/dreamer/lock.json", lock)
        with self.assertRaises(pm.MemoryError):
            pm.recover(self.root, run["run_id"], 60, False)
        pm.recover(self.root, run["run_id"], 60, True)
        self.assertFalse(lock_path.exists())
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())

    def test_crash_before_checkpoint_retry_deduplicates_proposals(self):
        run = pm.begin(self.root)
        self.prepare(run["run_id"], proposals=[self.proposal()])
        original = pm.atomic
        def fail_state(path, value):
            if path.name == "state.json":
                raise OSError("simulated interruption")
            original(path, value)
        with patch.object(pm, "atomic", side_effect=fail_state):
            with self.assertRaises(OSError):
                pm.finish(self.root, run["run_id"])
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())
        proposal_path = next((self.root / "memory/dreamer/proposals").glob("*.json"))
        before = proposal_path.read_bytes()
        pm.finish(self.root, run["run_id"])
        self.assertEqual(before, proposal_path.read_bytes())
        self.assertEqual(len(list((self.root / "memory/dreamer/proposals").glob("*.json"))), 1)

    def test_result_missing_review_and_unbacked_proposal_rejected(self):
        run = pm.begin(self.root)
        result = self.prepare(run["run_id"])
        result["reviewed_ids"] = []
        self.write_json(f"memory/dreamer/work/{run['run_id']}/result.json", result)
        with self.assertRaises(pm.MemoryError):
            pm.finish(self.root, run["run_id"])
        bad = {**self.proposal(), "source_ids": []}
        self.prepare(run["run_id"], proposals=[bad])
        with self.assertRaises(pm.MemoryError):
            pm.finish(self.root, run["run_id"])
        pm.abort(self.root, run["run_id"])

    def test_duplicate_id_and_missing_reference_rejected(self):
        self.write_record("memory/episodes/two.md", self.meta)
        with self.assertRaisesRegex(pm.MemoryError, "duplicate id"):
            pm.begin(self.root)
        (self.root / "memory/episodes/two.md").unlink()
        self.write_record("memory/episodes/one.md", {**self.meta, "source": ["id:unknown"]})
        with self.assertRaisesRegex(pm.MemoryError, "unknown source ID"):
            pm.begin(self.root)

    def test_invalid_metadata_cannot_enter_snapshot(self):
        for invalid in (
            {**self.meta, "status": "invented"},
            {**self.meta, "created_at": "2026-01-01"},
            {**self.meta, "project": "<placeholder>"},
            {**self.meta, "source": ["file:../outside.md"]},
        ):
            with self.subTest(metadata=invalid):
                self.write_record("memory/episodes/one.md", invalid)
                with self.assertRaises((pm.MemoryError, ValueError)):
                    pm.begin(self.root)
                self.assertFalse((self.root / "memory/dreamer/lock.json").exists())

    def test_fact_activation_requires_owner_and_verification(self):
        fact = {**self.meta, "id": "fact-001", "type": "semantic", "owner": "owner"}
        self.write_record("memory/facts/one.md", fact)
        with self.assertRaises(pm.MemoryError):
            pm.begin(self.root)
        fact.update(accepted_by="owner", last_verified="2026-01-01T00:00:00Z")
        self.write_record("memory/facts/one.md", fact)
        run = pm.begin(self.root)
        self.assertEqual(run["records"], 2)
        pm.abort(self.root, run["run_id"])

    def test_cli_partial_is_nonzero_and_leaves_no_checkpoint(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/project_memory.py"), "--root", str(self.root)]
        start = subprocess.run(command + ["begin"], capture_output=True, text=True)
        self.assertEqual(start.returncode, 0, start.stderr)
        run_id = json.loads(start.stdout)["run_id"]
        self.prepare(run_id, "partial")
        finish = subprocess.run(command + ["finish", "--run-id", run_id], capture_output=True, text=True)
        self.assertEqual(finish.returncode, 1, finish.stderr)
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())
        self.assertFalse((self.root / "memory/dreamer/lock.json").exists())

    def test_pin_prevents_archive_proposal(self):
        self.write_record("memory/episodes/one.md", {**self.meta, "pinned": True})
        run = pm.begin(self.root)
        self.prepare(run["run_id"], proposals=[{**self.proposal(), "kind": "archive"}])
        with self.assertRaisesRegex(pm.MemoryError, "pinned"):
            pm.finish(self.root, run["run_id"])
        pm.abort(self.root, run["run_id"])

    def test_due_facts_open_conflicts_and_backdated_inputs(self):
        fact = {**self.meta, "id": "fact-001", "type": "semantic", "owner": "owner", "accepted_by": "owner", "last_verified": "2020-01-01T00:00:00Z", "review_after": "2020-01-02"}
        conflict = {**self.meta, "id": "conflict-001", "type": "contradiction", "status": "open"}
        self.write_record("memory/facts/fact.md", fact)
        self.write_record("memory/contradictions/open.md", conflict)
        first = pm.begin(self.root)
        self.prepare(first["run_id"])
        pm.finish(self.root, first["run_id"])
        self.write_record("memory/episodes/backdated.md", {**self.meta, "id": "ep-backdated", "created_at": "2000-01-01T00:00:00Z"})
        next_run = pm.begin(self.root)
        self.assertEqual(next_run["records"], 3)
        pm.abort(self.root, next_run["run_id"])


class BoundedScanTests(unittest.TestCase):
    PRUNED = {"node_modules", ".venv", ".git", "build", "dist", "work", "vendor"}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bounded-scan-")
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "project"
        for name in (*pm.TYPES, "archive", "dreamer"):
            (self.root / "memory" / name).mkdir(parents=True)
            (self.root / "memory" / name / "README.md").write_text("# Folder\n", encoding="utf-8")
        (self.root / "memory/README.md").write_text("# Memory\n", encoding="utf-8")
        (self.root / "memory/config.json").write_text(pm.canonical({"version": 1, "schedule": {"frequency": "daily", "timezone": None, "local_time": None, "owner": None}, "review": {"episode_days": None}}), encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "README.md").write_text("# Home\n", encoding="utf-8")
        (self.root / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
        self.write_guide("[Home](../README.md#home)\n[Dependency](../node_modules/pkg/broken.md#not-checked)\n")
        for folder in ("node_modules/pkg", ".venv/lib", ".git-objects/.git", "build/out", "dist", "docs/node_modules/pkg", "docs/vendor/.git", "memory/dreamer/work/run"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
            (self.root / folder / "broken.md").write_text("[x](missing.md)\n", encoding="utf-8")
        (self.root / "docs/vendor/broken.md").write_text("[x](missing.md)\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_guide(self, body):
        (self.root / "docs/guide.md").write_text("# Guide\n\n" + body, encoding="utf-8")

    def spy(self):
        visited, reads = [], []
        real_scandir, real_read = os.scandir, Path.read_text
        def scandir(path="."):
            visited.append(Path(path).resolve())
            return real_scandir(path)
        def read_text(path, *args, **kwargs):
            reads.append(path.resolve())
            return real_read(path, *args, **kwargs)
        return visited, reads, patch.object(pm.os, "scandir", scandir), patch.object(Path, "read_text", read_text)

    def assert_inside_scope(self, paths):
        for path in paths:
            if path.is_relative_to(self.root):
                self.assertFalse(self.PRUNED & set(path.relative_to(self.root).parts), path)
            else:
                self.assertNotEqual(path, self.base / "outside")

    def test_dependency_trees_are_neither_listed_read_nor_copied(self):
        visited, reads, scan, read = self.spy()
        with scan, read:
            result = pm.validate(self.root)
            files = pm.managed_files(self.root)
        self.assertTrue(result["ok"])
        self.assert_inside_scope(visited + reads + files)
        self.assertIn(self.root / "docs/guide.md", files)
        self.assertNotIn(self.root / ".git", files)

    def test_selected_broken_link_still_fails(self):
        self.write_guide("[Missing](missing.md)\n")
        with self.assertRaisesRegex(pm.MemoryError, "broken"):
            pm.validate(self.root)

    def test_permission_denied_is_not_an_empty_scan(self):
        real = os.scandir
        def deny(path="."):
            if Path(path).resolve() == self.root / "docs":
                raise PermissionError("denied")
            return real(path)
        with patch.object(pm.os, "scandir", deny), self.assertRaisesRegex(pm.MemoryError, "permission denied"):
            pm.validate(self.root)

    def test_linked_directory_is_refused_without_reading_target(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text("[x](missing.md)\n", encoding="utf-8")
        link = self.root / "docs" / "linked"
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(link))
            else:
                os.symlink(outside, link, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"cannot create a directory link: {exc}")
        try:
            visited, reads, scan, read = self.spy()
            with scan, read:
                for call in (pm.validate, pm.managed_files):
                    with self.assertRaisesRegex(pm.MemoryError, "linked path"):
                        call(self.root)
            self.assertNotIn(outside, visited)
            self.assertNotIn(outside / "secret.md", reads)
        finally:
            os.rmdir(link) if os.name == "nt" else link.unlink()


@unittest.skipUnless("<Project name>" in (ROOT / "PROJECT.md").read_text(encoding="utf-8"), "template distribution only; adopted projects are covered by BoundedScanTests")
class PortableCopyTests(unittest.TestCase):
    def test_managed_manifest_copies_and_validates_within_bounds(self):
        files = pm.managed_files(ROOT)
        self.assertLessEqual(len(files), 400)
        self.assertLessEqual(sum(path.stat().st_size for path in files), 4_000_000)
        relative = [path.relative_to(ROOT) for path in files]
        for path in relative:
            self.assertFalse(BoundedScanTests.PRUNED & set(path.parts), path)
            self.assertTrue(path.parts[0] != "human-materials" or path.name in {"README.md", ".gitignore"}, path)
        with tempfile.TemporaryDirectory(prefix="template-copy-") as folder:
            destination = Path(folder) / "new-project"
            for path in relative:
                (destination / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, destination / path)
            result = pm.validate(destination.resolve())
            self.assertTrue(result["ok"])
            self.assertEqual(result["records"], 0)
            self.assertFalse(result["scheduler_configured"])


if __name__ == "__main__":
    unittest.main()
