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
import install
import memory_capture as mc
import project_memory as pm

EVENT = json.loads((ROOT / "tests/fixtures/automation/success-capture.json").read_text(encoding="utf-8"))["event"]
USER_HOOKS = {"description": "Team hooks", "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "python3 team_stop.py", "timeout": 5}]}],
    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 policy.py"}]}]}}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="setup-test-")
        self.root = Path(self.temp.name).resolve() / "proj with spaces \u00e9"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        self.client = patch.object(install, "codex_version", return_value="0.147.0")
        self.client.start()

    def tearDown(self):
        self.client.stop()
        self.temp.cleanup()

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def setup(self, apply=False, **kw):
        return install.setup(self.root, apply=apply, **kw)

    def hooks(self):
        return json.loads((self.root / ".codex/hooks.json").read_text(encoding="utf-8"))

    def test_dry_run_shows_the_plan_and_writes_nothing(self):
        before = self.snapshot()
        plan = self.setup()
        self.assertEqual((plan["exit"], plan["applied"]), (0, False))
        self.assertEqual({a["path"]: a["action"] for a in plan["actions"]},
                         {"memory/automation.json": "create", ".codex/hooks.json": "create", "AGENTS.md": "update", "memory/automation/install.json": "create"})
        for key in ("root", "python", "clients", "memory_policy", "removal", "next_steps"):
            self.assertIn(key, plan)
        self.assertEqual(before, self.snapshot())

    def test_apply_then_repeat_is_idempotent(self):
        result = self.setup(apply=True, project_id="demo")
        self.assertEqual((result["exit"], result["applied"], result["state"]), (0, True, "installed; Codex hook trust pending; probe pending"))
        hooks = self.hooks()["hooks"]
        self.assertEqual(sorted(hooks), sorted(install.EVENTS))
        for event in install.EVENTS:
            [group] = hooks[event]
            [entry] = group["hooks"]
            self.assertIn("hook.py", entry["command"])
            self.assertEqual(entry["timeout"], install.TIMEOUTS[event])
        self.assertEqual(pm.read_json(self.root / "memory/automation.json"), {"version": 1, "project_id": "demo", "adapters": ["codex"]})
        manifest = pm.read_json(self.root / "memory/automation/install.json")
        self.assertEqual((manifest["version"], manifest["project_id"], manifest["clients"]["codex"]["trust"]), (1, "demo", "pending"))
        self.assertIn("adapters/codex/hook.py", manifest["package_files"])
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8").count(install.BLOCK_START), 1)
        before = self.snapshot()
        again = self.setup(apply=True, project_id="demo")
        self.assertEqual({a["action"] for a in again["actions"]}, {"unchanged"})
        self.assertEqual(before, self.snapshot())
        self.assertTrue(pm.validate(self.root)["ok"])

    def test_user_hooks_and_rules_survive_setup_and_uninstall(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex/hooks.json").write_text(json.dumps(USER_HOOKS, indent=2), encoding="utf-8")
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8") + "\n## Team rule\nKeep this.\n"
        (self.root / "AGENTS.md").write_text(agents, encoding="utf-8")
        self.setup(apply=True)
        merged = self.hooks()
        self.assertEqual(merged["description"], "Team hooks")
        self.assertEqual(merged["hooks"]["PreToolUse"], USER_HOOKS["hooks"]["PreToolUse"])
        self.assertEqual(merged["hooks"]["Stop"][0], USER_HOOKS["hooks"]["Stop"][0])
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertIn("Keep this.", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        removed = install.uninstall(self.root, apply=True)
        self.assertEqual(removed["exit"], 0)
        self.assertEqual(self.hooks(), USER_HOOKS)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), agents)

    def test_conflicts_and_missing_client_stop_with_next_action(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex/hooks.json").write_text("{not json", encoding="utf-8")
        before = self.snapshot()
        result = self.setup(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (5, False))
        self.assertTrue(any(".codex/hooks.json" in step for step in result["next_steps"]))
        self.assertEqual(before, self.snapshot())
        (self.root / ".codex/hooks.json").unlink()
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "other", "adapters": []}), encoding="utf-8")
        self.assertEqual(self.setup(apply=True, project_id="demo")["exit"], 5)
        (self.root / "memory/automation.json").unlink()
        with patch.object(install, "codex_version", return_value=None):
            missing = self.setup(apply=True)
        self.assertEqual((missing["exit"], missing["applied"]), (4, False))
        self.assertTrue(any("Codex CLI" in step for step in missing["next_steps"]))
        self.assertFalse((self.root / ".codex/hooks.json").exists())

    def test_uninstall_keeps_memory_and_docs(self):
        self.setup(apply=True, project_id="example-project")
        self.assertTrue(mc.capture(self.root, EVENT)["saved"])
        episodes = sorted((self.root / "memory/episodes").glob("auto-*.md"))
        removed = install.uninstall(self.root, apply=True)
        self.assertEqual(removed["exit"], 0)
        self.assertEqual(episodes, sorted((self.root / "memory/episodes").glob("auto-*.md")))
        self.assertEqual(len(list((self.root / "memory/automation/receipts").glob("*.json"))), 1)
        for path in ("memory/automation.json", "memory/automation/install.json", ".codex/hooks.json"):
            self.assertFalse((self.root / path).exists(), path)
        self.assertNotIn(install.BLOCK_START, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue(pm.validate(self.root)["ok"])

    def test_newline_style_final_newline_and_hook_formatting_survive_setup_and_uninstall(self):
        for name, original in (("crlf", b"# Rules\r\n\r\nKeep CRLF.\r\n"), ("no-final-newline", b"# Rules\n\nNo final newline")):
            with self.subTest(name):
                (self.root / "AGENTS.md").write_bytes(original)
                hooks = '{\r\n    "description": "caf\u00e9 team",\r\n    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "team"}]}]}\r\n}\r\n'.encode("utf-8")
                (self.root / ".codex").mkdir(exist_ok=True)
                (self.root / ".codex/hooks.json").write_bytes(hooks)
                self.setup(apply=True)
                merged = (self.root / "AGENTS.md").read_bytes()
                self.assertTrue(merged.startswith(original))
                if name == "crlf":
                    self.assertEqual(merged.replace(b"\r\n", b"").count(b"\n"), 0)
                self.assertEqual(install.uninstall(self.root, apply=True)["exit"], 0)
                self.assertEqual((self.root / "AGENTS.md").read_bytes(), original)
                self.assertEqual((self.root / ".codex/hooks.json").read_bytes(), hooks)


    def test_marker_text_in_user_prose_is_never_treated_as_the_block(self):
        original = ("# Rules\nWe once used " + install.BLOCK_START + " inline.\nImportant user rule.\n").encode("utf-8")
        (self.root / "AGENTS.md").write_bytes(original)
        self.setup(apply=True)
        self.assertEqual(install.uninstall(self.root, apply=True)["exit"], 0)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), original)

    def test_edited_block_makes_uninstall_a_conflict_that_removes_nothing(self):
        self.setup(apply=True)
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace("Skip it for trivial replies.", "Skip it for trivial replies. Team addition."), encoding="utf-8")
        before = self.snapshot()
        result = install.uninstall(self.root, apply=True)
        self.assertEqual(result["exit"], 5)
        self.assertTrue(any("AGENTS.md" in step for step in result["next_steps"]))
        self.assertEqual(before, self.snapshot())

    def test_dangling_start_marker_line_stops_setup(self):
        (self.root / "AGENTS.md").write_text("# Rules\n" + install.BLOCK_START + "\nNo end marker.\n", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.setup(apply=True)["exit"], 5)
        self.assertEqual(before, self.snapshot())


    def test_uninstall_keeps_a_binding_setup_did_not_create(self):
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "mine", "adapters": ["claude-code"]}), encoding="utf-8")
        self.setup(apply=True)
        self.assertEqual(pm.read_json(self.root / "memory/automation.json")["adapters"], ["claude-code", "codex"])
        install.uninstall(self.root, apply=True)
        self.assertEqual(pm.read_json(self.root / "memory/automation.json"), {"version": 1, "project_id": "mine", "adapters": ["claude-code"]})


    def test_spaced_paths_without_short_names_run_in_powershell_and_cmd(self):
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if os.name != "nt" or not pwsh:
            self.skipTest("Windows shells only")
        import _winapi
        spaced_python = Path(self.temp.name) / "py with spaces"
        _winapi.CreateJunction(str(Path(sys.executable).resolve().parent), str(spaced_python))
        try:
            payload = json.dumps({"hook_event_name": "Stop", "session_id": "s", "turn_id": "t", "stop_hook_active": False, "last_assistant_message": "Done."}).encode()
            for python, shells in ((Path(sys.executable).resolve(), ("cmd", "pwsh")), (spaced_python / Path(sys.executable).name, ("pwsh",))):
                with patch.object(install, "short_path", return_value=None), patch.object(install.sys, "executable", str(python)):
                    command = install.setup(self.root)["hook_command"]
                for shell in shells:
                    argv = f'cmd /d /s /c "{command}"' if shell == "cmd" else [pwsh, "-NoProfile", "-Command", command]
                    run = subprocess.run(argv, input=payload, capture_output=True, cwd=self.root, timeout=60)
                    self.assertEqual((run.returncode, run.stdout.strip()[:1]), (0, b"{"), (shell, command, run.stderr))
        finally:
            os.rmdir(spaced_python)


    def test_generated_hook_command_runs_from_the_system_shell(self):
        self.setup(apply=True)
        command = self.hooks()["hooks"]["Stop"][0]["hooks"][0]["command"]
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s-1", "turn_id": "t-1", "stop_hook_active": False, "last_assistant_message": "Done."})
        run = subprocess.run(command, shell=True, input=payload.encode("utf-8"), capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {})
        self.assertEqual(len(list((self.root / "memory/automation/receipts").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()

