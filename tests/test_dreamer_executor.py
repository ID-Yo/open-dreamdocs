import copy
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
import dreamer_executor as de


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dreamer-executor-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        pm.atomic(self.root / "memory/automation.json", {"version": 1, "project_id": "example-project", "adapters": ["codex"]})
        meta = {"id": "ep-review", "type": "episodic", "status": "active", "project": "example-project", "scope": "build",
                "created_at": "2026-01-01T00:00:00Z", "source": ["file:docs/overview/platform.md"]}
        (self.root / "memory/episodes/review.md").write_text("---\n" + json.dumps(meta) + "\n---\n# Review\nSynthetic source needs careful verification.\n", encoding="utf-8")
        self.config = {"version": 1, "project_id": "example-project", "paused": False, "evidence_files": ["docs/governance/promotion-rules.md"],
                       "executor": {"id": "operator", "kind": "operator", "argv": None, "timeout_seconds": 60,
                                    "max_records": 100, "max_input_bytes": 1048576, "max_result_bytes": 1048576, "max_proposals": 20},
                       "scheduler": None}
        self.configure()

    def configure(self):
        pm.atomic(self.root / de.CONFIG, self.config)

    def result(self, run, status="success"):
        work = self.root / "memory/dreamer/work" / run
        snapshot = pm.read_json(work / "snapshot.json")
        value = {"run_id": run, "status": status, "summary": "Reviewed synthetic source; candidate requires owner review.",
                 "reviewed_ids": [r["metadata"]["id"] for r in snapshot["records"]],
                 "proposals": [{"kind": "fact", "title": "Synthetic candidate", "source_ids": ["ep-review"], "body": "Candidate only, based on the cited synthetic episode."}]}
        pm.atomic(work / "result.json", value)
        return value

    def test_manual_operator_is_explicit_and_commits_readback_without_promotion_or_config_migration(self):
        before_config = (self.root / "memory/config.json").read_bytes()
        before_doc = (self.root / "docs/overview/platform.md").read_bytes()
        begun = de.begin(self.root, "operator")
        self.assertEqual(begun["state"], "prepared")
        self.assertIsNone(begun["execution"]["started_at"])
        run = begun["run_id"]
        self.assertEqual(de.start(self.root, run, "operator")["state"], "running")
        self.result(run)
        result = de.finish(self.root, run, "operator")
        self.assertEqual((result["exit"], result["state"]), (0, "success"), result)
        execution = result["execution"]
        self.assertTrue(execution["started_at"] and execution["finished_at"])
        self.assertEqual(execution["project_id"], "example-project")
        self.assertEqual(execution["executor_id"], "operator")
        self.assertEqual(execution["checkpoint"]["last_run_id"], run)
        self.assertEqual(execution["result_sha256"], pm.digest((self.root / "memory/dreamer/work" / run / "result.json").read_bytes()))
        self.assertEqual(before_config, (self.root / "memory/config.json").read_bytes())
        self.assertEqual(before_doc, (self.root / "docs/overview/platform.md").read_bytes())
        self.assertEqual(list((self.root / "memory/facts").glob("*.md")), [self.root / "memory/facts/README.md"])
        self.assertEqual(de.status(self.root)["last_execution"]["state"], "success")
        import memory_health as mh
        self.assertEqual(mh.doctor(self.root)["dreamer"]["executor_observation"]["last_execution"]["state"], "success")

    def test_missing_paused_denied_executor_and_shared_locks_do_not_start_work(self):
        original = copy.deepcopy(self.config)
        for change in (lambda: self.config.update(executor=None), lambda: self.config.update(paused=True)):
            change(); self.configure()
            result = de.begin(self.root, "operator")
            self.assertNotEqual(result["exit"], 0)
            self.assertFalse((self.root / "memory/dreamer/lock.json").exists())
            self.config = copy.deepcopy(original)
        self.configure()
        self.assertNotEqual(de.begin(self.root, "wrong-operator")["exit"], 0)
        for name in ("command.lock", "lock.json"):
            path = self.root / "memory/dreamer" / name
            path.write_text("live owner", encoding="utf-8")
            self.assertNotEqual(de.begin(self.root, "operator")["exit"], 0)
            self.assertEqual(path.read_text(), "live owner")
            path.unlink()

    def test_failed_partial_bad_result_budget_and_changed_evidence_never_advance_checkpoint(self):
        for mode in ("partial", "failed", "source_changed", "budget", "invalid"):
            begun = de.begin(self.root, "operator")
            run = begun["run_id"]
            de.start(self.root, run, "operator")
            result = self.result(run, mode if mode in {"partial", "failed"} else "success")
            if mode == "source_changed":
                doc = self.root / "docs/overview/platform.md"
                previous = doc.read_bytes(); doc.write_bytes(previous + b"\nchanged during review\n")
            if mode == "budget":
                result["proposals"] *= 21
            if mode == "invalid":
                result["reviewed_ids"] = []
            pm.atomic(self.root / "memory/dreamer/work" / run / "result.json", result)
            self.assertNotEqual(de.finish(self.root, run, "operator")["exit"], 0)
            self.assertFalse((self.root / "memory/dreamer/state.json").exists())
            if (self.root / "memory/dreamer/lock.json").exists():
                pm.abort(self.root, run)
            if mode == "source_changed":
                doc.write_bytes(previous)

    def test_finish_requires_actual_start_and_matching_config_identity(self):
        run = de.begin(self.root, "operator")["run_id"]
        self.result(run)
        self.assertNotEqual(de.finish(self.root, run, "operator")["exit"], 0)
        self.assertNotEqual(de.start(self.root, run, "wrong")["exit"], 0)
        de.start(self.root, run, "operator")
        self.config["executor"]["id"] = "other"
        self.configure()
        self.assertNotEqual(de.finish(self.root, run, "other")["exit"], 0)
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())

    def test_cli_manual_begin_start_finish_and_unconfigured_are_json(self):
        def cli(*args):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/dreamdocs.py"), "--root", str(self.root), "dreamer", *args], capture_output=True, timeout=30)
            return result.returncode, json.loads(result.stdout)
        code, begun = cli("begin", "--executor", "operator")
        self.assertEqual(code, 0)
        run = begun["run_id"]
        self.assertEqual(cli("start", "--run-id", run, "--executor", "operator")[0], 0)
        self.result(run)
        self.assertEqual(cli("finish", "--run-id", run, "--executor", "operator")[0], 0)
        self.config["executor"] = None; self.configure()
        code, result = cli("run", "--executor", "operator")
        self.assertEqual((code, result["state"]), (4, "unconfigured"))

    def test_owned_timeout_joins_descendants_and_uncertain_cleanup_keeps_lock(self):
        import os
        import time
        pid_file = Path(self.temp.name) / "child.pid"
        self.command("import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\nPath(" + repr(str(pid_file)) + ").write_text(str(p.pid))\ntime.sleep(30)\n")
        self.config["executor"]["timeout_seconds"] = 1; self.configure()
        result = de.run(self.root, "operator")
        self.assertEqual(result["state"], "timed_out", result)
        child = int(pid_file.read_text())
        def alive():
            if os.name == "nt":
                import ctypes as ct
                kernel = ct.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = ct.c_void_p
                kernel.GetExitCodeProcess.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ulong)]
                kernel.CloseHandle.argtypes = [ct.c_void_p]
                handle = kernel.OpenProcess(0x1000, False, child)
                if not handle:
                    return False
                code = ct.c_ulong()
                kernel.GetExitCodeProcess(handle, ct.byref(code)); kernel.CloseHandle(handle)
                return code.value == 259
            try:
                os.kill(child, 0)
                return True
            except ProcessLookupError:
                return False
        until = time.monotonic() + 3
        while alive() and time.monotonic() < until:
            time.sleep(0.02)
        self.assertFalse(alive(), "owned child survived timeout cleanup")
        with patch.object(de, "OwnedProcess", side_effect=de.ProcessTreeUncertain("injected uncertain cleanup")):
            self.assertEqual(de.run(self.root, "operator")["state"], "blocked")
        self.assertTrue((self.root / "memory/dreamer/lock.json").exists())

    def command(self, body):
        path = Path(self.temp.name) / "selected_executor.py"
        path.write_text(body, encoding="utf-8")
        self.config["executor"].update(kind="command", argv=[sys.executable, "-B", str(path), "{snapshot}", "{result}"])
        self.configure()

    def test_real_command_process_has_identity_budget_hashes_and_checkpoint_readback(self):
        self.command("import json,sys\nfrom pathlib import Path\ns=json.loads(Path(sys.argv[1]).read_text())\nr={'run_id':s['run_id'],'status':'success','summary':'Synthetic transport only.','reviewed_ids':[r['metadata']['id'] for r in s['records']],'proposals':[]}\nPath(sys.argv[2]).write_text(json.dumps(r))\n")
        result = de.run(self.root, "operator")
        self.assertEqual(result["exit"], 0, result)
        self.assertEqual(result["execution"]["process_exit"], 0)
        self.assertTrue(result["execution"]["pid"])
        self.assertTrue(result["execution"]["process_finished_at"])
        self.assertEqual(result["execution"]["state"], "success")

    def test_command_denial_failure_and_timeout_are_recoverable_and_owned_process_is_joined(self):
        for kind in ("denied", "failure", "timeout"):
            self.command("import sys,time\n" + ("time.sleep(10)\n" if kind == "timeout" else "sys.exit(7)\n"))
            if kind == "denied":
                self.config["executor"]["argv"][0] = str(Path(self.temp.name) / "missing.exe")
            self.config["executor"]["timeout_seconds"] = 1
            self.configure()
            result = de.run(self.root, "operator")
            self.assertNotEqual(result["exit"], 0, result)
            self.assertFalse((self.root / "memory/dreamer/state.json").exists())
            self.assertFalse((self.root / "memory/dreamer/lock.json").exists())
            self.assertIn(result["state"], {"blocked", "failed", "timed_out"})

    def test_dispatch_rechecks_config_and_does_not_execute_an_outdated_command(self):
        self.command("import sys\nsys.exit(0)\n")
        original = de.begin
        def changed(*args, **kwargs):
            prepared = original(*args, **kwargs)
            self.config["executor"]["argv"][0] = str(Path(self.temp.name) / "changed.exe")
            self.configure()
            return prepared
        with patch.object(de, "begin", side_effect=changed), patch.object(de, "OwnedProcess") as launch:
            result = de.run(self.root, "operator")
        self.assertEqual(result["state"], "blocked")
        launch.assert_not_called()
        self.assertTrue((self.root / "memory/dreamer/lock.json").exists())

    def test_runtime_receipts_refuse_effective_git_exposure_or_tracked_private_config(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        ignore = self.root / ".dreamdocs/.gitignore"
        ignore.write_text("*\n!dreamer-runs/\n!dreamer-runs/*.json\n", encoding="utf-8")
        result = de.begin(self.root, "operator")
        self.assertEqual(result["state"], "blocked")
        self.assertFalse((self.root / de.RUNS).exists())
        self.assertFalse((self.root / "memory/dreamer/lock.json").exists())
        ignore.write_text("*\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", "--", de.CONFIG], cwd=self.root, check=True, capture_output=True, timeout=10)
        self.assertEqual(de.begin(self.root, "operator")["state"], "blocked")

    def test_interrupted_finish_or_orphan_proposal_never_reports_a_committed_success(self):
        run = de.begin(self.root, "operator")["run_id"]
        de.start(self.root, run, "operator")
        self.result(run)
        original = pm.atomic
        def fail(path, value):
            if path == self.root / "memory/dreamer/state.json":
                raise OSError("injected checkpoint write loss")
            return original(path, value)
        with patch.object(pm, "atomic", side_effect=fail):
            result = de.finish(self.root, run, "operator")
        self.assertNotEqual(result["exit"], 0)
        self.assertFalse((self.root / "memory/dreamer/state.json").exists())
        self.assertTrue((self.root / "memory/dreamer/lock.json").exists())
        self.assertNotEqual(de.status(self.root)["last_execution"]["state"], "success")


if __name__ == "__main__":
    unittest.main()
