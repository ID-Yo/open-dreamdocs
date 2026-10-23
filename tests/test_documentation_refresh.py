import copy
from datetime import datetime, timedelta, timezone
import json
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
import documentation_refresh as dr
import human_materials as hm


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="docs-refresh-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        (self.root / ".dreamdocs").mkdir()
        pm.atomic(self.root / "memory/automation.json", {"version": 1, "project_id": "example-project", "adapters": ["codex"]})
        self.source = "memory/episodes/research.md"
        meta = {"id": "research", "type": "episodic", "status": "active", "project": "example-project", "scope": "research",
                "created_at": "2026-01-02T00:00:00Z", "source": ["ref:reviewed-research"]}
        self.put(self.source, "---\n" + json.dumps(meta) + "\n---\n# Research\n\nThe reviewed interviews cover three shops, not a market estimate.\n")
        self.put("docs/marketing/research.md", "# Research\n\nInterviews are still a draft.\n")
        self.target = "docs/marketing/research.md"
        accepted = "2026-01-04T00:00:00Z"
        task = {"id": "research-task", "manager": "manager", "executor": "writer", "status": "done", "start_approved": True,
                "next_action": "Owner review of documentation proposal", "acceptance": ["Review source and exact candidate"],
                "evidence": ["ref:task-1"], "updated_at": accepted, "next_check_at": None, "handoffs": [], "blocker": None,
                "candidate": {"id": "research-v2", "author": "writer", "source_hashes": {self.source: self.sha(self.source)}},
                "review": {"candidate": "research-v2", "reviewer": "reviewer", "verdict": "approve", "reviewed_at": "2026-01-03T00:00:00Z", "evidence": ["ref:independent-review"]},
                "accepted": {"candidate": "research-v2", "by": "manager", "accepted_at": accepted, "evidence": ["ref:manager-accepted-v2"]}}
        self.tasks = {"version": 1, "reconciled_at": pm.now(), "next_check_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                      "runtime": {"scheduler": "not_configured", "host": "unknown", "observed_at": None, "next_check_at": None, "evidence": []}, "tasks": [task]}
        self.policy = {"version": 1, "project_id": "example-project", "manager": "manager", "task_file": ".dreamdocs/tasks.json",
                       "allowed_targets": [self.target, "docs/status/current-state.md", "docs/00-index.md", "docs/marketing/README.md"], "human_inventory": True}
        self.save_control()
        self.request = {"version": 1, "project_id": "example-project", "task_id": "research-task", "candidate": "research-v2",
                        "task_snapshot_sha256": self.sha(".dreamdocs/tasks.json"), "title": "Reviewed interview scope",
                        "sources": [{"path": self.source, "sha256": self.sha(self.source), "classification": "reviewed_research"}],
                        "changes": [{"path": self.target, "sha256": self.sha(self.target), "title": "Interview research", "source_paths": [self.source],
                                     "before": "Interviews are still a draft.", "after": "Reviewed interviews cover three shops; total market size remains unknown."}],
                        "human_inventory": True, "dreamer_run_id": None}

    def put(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))

    def sha(self, path):
        return pm.digest((self.root / path).read_bytes())

    def save_control(self):
        pm.atomic(self.root / ".dreamdocs/tasks.json", self.tasks)
        pm.atomic(self.root / ".dreamdocs/documentation-policy.json", self.policy)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_accepted_change_proposes_dated_pages_status_and_routing_without_promoting(self):
        before = self.snapshot()
        result = dr.propose(self.root, self.request)
        self.assertEqual(result["exit"], 0, result)
        self.assertEqual(before, self.snapshot())
        proposal = result["proposal"]
        self.assertEqual(proposal["status"], "proposed")
        self.assertTrue(proposal["owner_review_required"])
        self.assertEqual(proposal["accepted_candidate"], "research-v2")
        edits = {e["path"]: e for e in proposal["edits"]}
        self.assertEqual(set(edits), set(self.policy["allowed_targets"]))
        self.assertIn("total market size remains unknown", edits[self.target]["proposed_text"])
        self.assertIn("Interviews are still a draft.", edits[self.target]["proposed_text"])
        self.assertIn("research.md", edits["docs/00-index.md"]["proposed_text"])
        self.assertIn("research-v2", edits["docs/status/current-state.md"]["proposed_text"])
        self.assertEqual(edits[self.target]["before_sha256"], self.sha(self.target))
        saved = dr.propose(self.root, self.request, write=True)
        self.assertTrue(saved["written"])
        self.assertTrue(saved["path"].startswith(".dreamdocs/documentation-refresh/"))
        self.assertTrue(dr.check(self.root, saved["path"])["ok"])
        for path, data in before.items():
            self.assertEqual((self.root / path).read_bytes(), data, path)

    def test_unaccepted_wrong_candidate_own_review_and_owner_target_rule_refuse(self):
        cases = [lambda: self.tasks["tasks"][0].update(status="review"),
                 lambda: self.tasks["tasks"][0]["accepted"].update(candidate="older-draft"),
                 lambda: self.tasks["tasks"][0]["review"].update(reviewer="writer"),
                 lambda: self.policy["allowed_targets"].remove(self.target)]
        for mutate in cases:
            tasks, policy = copy.deepcopy(self.tasks), copy.deepcopy(self.policy)
            mutate()
            self.save_control()
            self.request["task_snapshot_sha256"] = self.sha(".dreamdocs/tasks.json")
            before = self.snapshot()
            result = dr.propose(self.root, self.request, write=True)
            self.assertNotEqual(result["exit"], 0)
            self.assertEqual(before, self.snapshot())
            self.tasks, self.policy = tasks, policy

    def test_stale_source_target_snapshot_and_missing_candidate_source_binding_refuse(self):
        original = copy.deepcopy(self.request)
        for which in ("source", "target", "snapshot", "candidate_binding"):
            self.request = copy.deepcopy(original)
            tasks = copy.deepcopy(self.tasks)
            if which == "source":
                self.request["sources"][0]["sha256"] = "0" * 64
            elif which == "target":
                self.request["changes"][0]["sha256"] = "0" * 64
            elif which == "snapshot":
                self.request["task_snapshot_sha256"] = "0" * 64
            else:
                self.tasks["tasks"][0]["candidate"]["source_hashes"] = {}
                self.save_control()
                self.request["task_snapshot_sha256"] = self.sha(".dreamdocs/tasks.json")
            before = self.snapshot()
            self.assertNotEqual(dr.propose(self.root, self.request, write=True)["exit"], 0)
            self.assertEqual(before, self.snapshot())
            self.tasks = tasks
            self.save_control()

    def test_snapshot_digest_is_required_even_when_acceptance_changes_after_the_request(self):
        for value in (None, "", "not-a-digest", "0" * 63, [], {}, True):
            self.request["task_snapshot_sha256"] = value
            for changed in (False, True):
                if changed:
                    self.tasks["tasks"][0]["accepted"]["evidence"] = ["ref:changed-after-request"]
                    self.save_control()
                before = self.snapshot()
                result = dr.propose(self.root, self.request, write=True)
                self.assertEqual(result["exit"], 2, (value, changed))
                self.assertFalse(result["written"])
                self.assertEqual(before, self.snapshot())

    def test_snapshot_change_after_initial_read_prevents_publication(self):
        from contextlib import contextmanager
        original = pm.operation
        @contextmanager
        def changed(root):
            self.tasks["tasks"][0]["accepted"]["evidence"] = ["ref:changed-before-lock"]
            self.save_control()
            with original(root):
                yield
        with patch.object(pm, "operation", side_effect=changed):
            result = dr.propose(self.root, self.request, write=True)
        self.assertEqual(result["exit"], 2)
        self.assertFalse(result["written"])
        self.assertFalse((self.root / dr.FOLDER).exists())

    def test_effective_git_exclusion_refuses_overriding_negations_before_publication(self):
        self.put(".gitignore", "!/.dreamdocs/\n")
        for rule in ("*", "/documentation-refresh/"):
            self.put(".dreamdocs/.gitignore", rule + "\n!documentation-refresh/\n!documentation-refresh/*.json\n")
            sidecar = dr.propose(self.root, self.request)["path"]
            ignored = subprocess.run(["git", "check-ignore", "-q", "--", sidecar], cwd=self.root, timeout=10)
            self.assertEqual(ignored.returncode, 1)
            before = self.snapshot()
            result = dr.propose(self.root, self.request, write=True)
            self.assertEqual(result["exit"], 2, result.get("findings"))
            self.assertFalse(result["written"])
            self.assertFalse((self.root / sidecar).exists())
            self.assertEqual(before, self.snapshot())

    def test_effective_exclusion_preserves_owner_rules_and_hides_sidecar_from_git_listing(self):
        self.put(".gitignore", "!/.dreamdocs/\n")
        rules = "documentation-refresh/*.json\n!*.md\n"
        self.put(".dreamdocs/.gitignore", rules)
        result = dr.propose(self.root, self.request, write=True)
        self.assertEqual(result["exit"], 0, result.get("findings"))
        self.assertTrue(result["written"])
        self.assertEqual((self.root / ".dreamdocs/.gitignore").read_text(), rules)
        listed = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", result["path"]],
                                cwd=self.root, check=True, capture_output=True, timeout=10)
        self.assertEqual(listed.stdout, b"")

    def test_tracked_sidecar_destination_is_refused_even_with_an_ignore_rule(self):
        saved = dr.propose(self.root, self.request, write=True)
        sidecar = saved["path"]
        subprocess.run(["git", "add", "-f", "--", sidecar], cwd=self.root, check=True, capture_output=True, timeout=10)
        for absent in (False, True):
            if absent:
                (self.root / sidecar).unlink()
            before = self.snapshot()
            result = dr.propose(self.root, self.request, write=True)
            self.assertEqual(result["exit"], 2)
            self.assertFalse(result["written"])
            self.assertEqual(before, self.snapshot())

    def test_git_unavailable_or_non_git_project_refuses_write_but_preserves_preview(self):
        for error in (FileNotFoundError("git unavailable"), subprocess.TimeoutExpired("git", 5)):
            before = self.snapshot()
            with patch.object(dr.subprocess, "run", side_effect=error):
                self.assertEqual(dr.propose(self.root, self.request)["exit"], 0)
                result = dr.propose(self.root, self.request, write=True)
            self.assertEqual(result["exit"], 2)
            self.assertFalse(result["written"])
            self.assertEqual(before, self.snapshot())
        held = Path(self.temp.name) / "held-test-git"
        (self.root / ".git").rename(held)
        try:
            before = self.snapshot()
            self.assertEqual(dr.propose(self.root, self.request)["exit"], 0)
            self.assertEqual(dr.propose(self.root, self.request, write=True)["exit"], 2)
            self.assertEqual(before, self.snapshot())
        finally:
            held.rename(self.root / ".git")

    def test_sidecar_recheck_detects_rollback_acceptance_and_source_target_changes(self):
        saved = dr.propose(self.root, self.request, write=True)
        self.put(self.target, "rolled back owner revision")
        result = dr.check(self.root, saved["path"])
        self.assertFalse(result["ok"])
        self.assertIn(self.target, result["changed_paths"])
        self.tasks["tasks"][0]["accepted"]["candidate"] = "old-version"
        self.save_control()
        self.assertIn(".dreamdocs/tasks.json", dr.check(self.root, saved["path"])["changed_paths"])

    def test_material_inventory_add_move_remove_partial_and_unparseable_never_opens_originals(self):
        self.put("human-materials/new/private.pdf", "SECRET ORIGINAL MUST NOT BE READ")
        self.put("human-materials/partial.bin", "PARTIAL ORIGINAL")
        self.put("human-materials/bad.bin", "UNPARSEABLE ORIGINAL")
        index = self.root / "human-materials/README.md"
        table = "| [old](old.pdf) | Filename only; content not reviewed. | PDF | unknown | unread | — |\n| [partial](partial.bin) | First page only. | BIN | unknown | partial | 2026-01-01 |\n| [bad](bad.bin) | Reader failed. | BIN | unknown | unparseable | — |\n"
        text = index.read_text(encoding="utf-8").replace("|---|---|---|---|---|---|", "|---|---|---|---|---|---|\n" + table)
        self.put("human-materials/README.md", text)
        read = Path.read_bytes
        def guard(path):
            if path.is_relative_to(self.root / "human-materials") and path.name not in {"README.md", ".gitignore"}:
                raise AssertionError("Original opened: " + str(path))
            return read(path)
        with patch.object(Path, "read_bytes", guard):
            result = dr.propose(self.root, self.request)
        self.assertEqual(result["exit"], 0, result)
        materials = result["proposal"]["human_materials"]
        self.assertEqual(materials["scope"], "selected human-materials tree only; coverage is not extraction")
        self.assertIn("new/private.pdf", materials["missing_rows"])
        self.assertIn("old.pdf", materials["stale_rows"])
        self.assertEqual(materials["reported_statuses"]["partial.bin"], "partial")
        self.assertFalse(materials["public_export_allowed"])
        proposed = next(e["proposed_text"] for e in result["proposal"]["edits"] if e["path"] == "human-materials/README.md")
        self.assertIn("new/private.pdf", proposed)
        self.assertIn("| unread |", proposed)
        self.assertIn("old.pdf", proposed)  # retain stale row history for review
        self.assertNotIn("SECRET ORIGINAL", json.dumps(result))
        self.assertFalse(hm.public_export(self.root)["ok"])

    def test_original_source_and_forged_or_uncommitted_dreamer_result_are_rejected(self):
        self.request["sources"][0]["path"] = "human-materials/private.pdf"
        self.assertNotEqual(dr.propose(self.root, self.request)["exit"], 0)
        self.request["sources"][0]["path"] = self.source
        self.request["dreamer_run_id"] = "uncommitted-run"
        self.assertNotEqual(dr.propose(self.root, self.request)["exit"], 0)

    def test_committed_dreamer_report_needs_matching_checkpoint_and_acceptance(self):
        begun = pm.begin(self.root)
        run = begun["run_id"]
        snapshot = pm.read_json(self.root / "memory/dreamer/work" / run / "snapshot.json")
        pm.atomic(self.root / "memory/dreamer/work" / run / "result.json", {"run_id": run, "status": "success", "summary": "Synthetic review transport only.",
                  "reviewed_ids": [r["metadata"]["id"] for r in snapshot["records"]], "proposals": []})
        pm.finish(self.root, run)
        report = "memory/dreamer/reports/" + run + ".json"
        self.tasks["tasks"][0]["candidate"]["source_hashes"][report] = self.sha(report)
        self.tasks["tasks"][0]["review"]["reviewed_at"] = pm.now()
        self.tasks["tasks"][0]["accepted"]["accepted_at"] = pm.now()
        self.tasks["tasks"][0]["updated_at"] = pm.now()
        self.tasks["reconciled_at"] = pm.now()
        self.save_control()
        self.request["task_snapshot_sha256"] = self.sha(".dreamdocs/tasks.json")
        self.request["sources"].append({"path": report, "sha256": self.sha(report), "classification": "runtime_observation"})
        self.request["dreamer_run_id"] = run
        self.assertEqual(dr.propose(self.root, self.request)["exit"], 0)
        state = pm.read_json(self.root / "memory/dreamer/state.json")
        state["last_run_id"] = "older-checkpoint"
        pm.atomic(self.root / "memory/dreamer/state.json", state)
        self.assertNotEqual(dr.propose(self.root, self.request)["exit"], 0)

    def test_public_export_guard_rejects_populated_index_even_when_original_is_missing(self):
        self.assertTrue(hm.public_export(self.root)["ok"])
        self.put("human-materials/README.md", "| Material | Description / purpose | Format | Tags | Review status | Reviewed |\n|---|---|---|---|---|---|\n| [Private](missing.pdf) | private filename | PDF | unknown | unread | — |\n")
        self.assertFalse(hm.public_export(self.root)["ok"])

    def test_public_export_guard_rejects_private_prose_outside_an_empty_table(self):
        index = self.root / "human-materials/README.md"
        self.put("human-materials/README.md", index.read_text(encoding="utf-8") + "\nPrivate project notes outside the table.\n")
        self.assertFalse(hm.public_export(self.root)["ok"])

    def test_material_candidate_index_is_coverage_valid_without_opening_originals(self):
        self.put("human-materials/new (draft) #1.pdf", "private synthetic original")
        result = dr.propose(self.root, self.request)
        candidate = next(e for e in result["proposal"]["edits"] if e["path"] == "human-materials/README.md")
        self.put(candidate["path"], candidate["proposed_text"])
        self.assertEqual(hm.check(self.root), [])

    def test_write_refuses_active_writer_and_changes_after_preflight(self):
        pm.atomic(self.root / "memory/dreamer/command.lock", {"owner_pid": 1, "acquired_at": pm.now()})
        before = self.snapshot()
        self.assertNotEqual(dr.propose(self.root, self.request, write=True)["exit"], 0)
        self.assertEqual(before, self.snapshot())
        (self.root / "memory/dreamer/command.lock").unlink()
        from contextlib import contextmanager
        original = pm.operation
        @contextmanager
        def changed(root):
            self.put(self.target, "Concurrent owner edit")
            with original(root):
                yield
        with patch.object(pm, "operation", side_effect=changed):
            result = dr.propose(self.root, self.request, write=True)
        self.assertNotEqual(result["exit"], 0)
        self.assertFalse((self.root / dr.FOLDER).exists())
        self.assertEqual((self.root / self.target).read_text(), "Concurrent owner edit")

    def test_new_page_replay_tamper_and_material_inventory_limit(self):
        (self.root / self.target).unlink()
        self.request["changes"][0].update(sha256=None, before="")
        saved = dr.propose(self.root, self.request, write=True)
        self.assertEqual(saved["exit"], 0, saved)
        self.assertFalse((self.root / self.target).exists())
        replay = dr.propose(self.root, self.request, write=True)
        self.assertFalse(replay["written"])
        self.assertEqual(saved["proposal"], replay["proposal"])
        file = self.root / saved["path"]
        edited = pm.read_json(file)
        edited["edits"][0]["proposed_text"] += "forged after preparation"
        pm.atomic(file, edited)
        self.assertFalse(dr.check(self.root, saved["path"])["ok"])
        with patch.object(hm, "MAX_ENTRIES", 0):
            self.assertNotEqual(dr.propose(self.root, self.request)["exit"], 0)

    def test_tampered_sidecar_cannot_make_recheck_open_original_materials(self):
        saved = dr.propose(self.root, self.request, write=True)
        self.put("human-materials/private.pdf", "Private original")
        sidecar = self.root / saved["path"]
        data = pm.read_json(sidecar)
        data["dependencies"]["human-materials/private.pdf"] = "0" * 64
        pm.atomic(sidecar, data)
        read = Path.read_bytes
        def guarded(path):
            if path == self.root / "human-materials/private.pdf":
                raise AssertionError("Original opened by tampered dependency")
            return read(path)
        with patch.object(Path, "read_bytes", guarded):
            self.assertFalse(dr.check(self.root, saved["path"])["ok"])

    def test_cli_invalid_input_is_json_and_no_side_effects(self):
        path = self.root / ".dreamdocs/request.json"
        pm.atomic(path, self.request)
        before = self.snapshot()
        run = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/documentation_refresh.py"), "--root", str(self.root), "propose", "--request", ".dreamdocs/request.json"], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["proposal"]["status"], "proposed")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
