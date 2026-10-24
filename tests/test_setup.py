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
        self.claude = patch.object(install, "claude_version", return_value="2.1.273")
        self.claude.start()

    def tearDown(self):
        self.claude.stop()
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
                         {"memory/automation.json": "create", ".codex/hooks.json": "create", ".codex/.gitignore": "create", "AGENTS.md": "update", "memory/automation/install.json": "create"})
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


    def test_created_hook_file_is_git_ignored_and_a_tracked_one_is_warned_about(self):
        self.setup(apply=True)
        self.assertEqual((self.root / ".codex/.gitignore").read_text(encoding="utf-8"), "hooks.json\n")
        install.uninstall(self.root, apply=True)
        self.assertFalse((self.root / ".codex").exists())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".codex").mkdir()
        (self.root / ".codex/hooks.json").write_text('{"hooks": {}}', encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", ".codex/hooks.json"], check=True)
        plan = self.setup()
        self.assertTrue(any("tracked by Git" in w for w in plan["warnings"]), plan["warnings"])
        self.assertNotIn(".codex/.gitignore", {a["path"] for a in plan["actions"]})


    def test_non_git_project_gets_a_codex_trust_warning(self):
        self.assertTrue(any("not inside a Git repository" in w for w in self.setup()["warnings"]))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.assertFalse(any("Git repository" in w for w in self.setup()["warnings"]))


    def test_claude_code_setup_merges_local_settings_and_claude_md_and_uninstall_restores_them(self):
        shared = b'{\n  "permissions": {"allow": ["Bash(git status)"]}\n}\n'
        local = b'{\r\n  "permissions": {"allow": ["Bash(npm test)"]},\r\n  "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "team-stop"}]}]}\r\n}\r\n'
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_bytes(shared)
        (self.root / ".claude/settings.local.json").write_bytes(local)
        claude_md = b"# Team notes\r\nUse small commits.\r\n"
        (self.root / "CLAUDE.md").write_bytes(claude_md)
        result = self.setup(apply=True, project_id="demo", clients=("claude-code",))
        self.assertEqual((result["exit"], result["applied"]), (0, True), result["next_steps"])
        self.assertEqual((self.root / ".claude/settings.json").read_bytes(), shared)
        merged = json.loads((self.root / ".claude/settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(merged["permissions"], {"allow": ["Bash(npm test)"]})
        self.assertEqual(merged["hooks"]["Stop"][0], {"hooks": [{"type": "command", "command": "team-stop"}]})
        self.assertEqual(sorted(merged["hooks"]), sorted(install.CLAUDE_EVENTS))
        ours = merged["hooks"]["StopFailure"][0]["hooks"][0]
        self.assertEqual(set(ours), {"type", "command", "args", "timeout"})
        self.assertEqual(ours["args"], ["-B", "${CLAUDE_PROJECT_DIR}/adapters/claude-code/hook.py"])
        self.assertEqual((self.root / "CLAUDE.md").read_bytes().count(install.BLOCK_START.encode()), 1)
        self.assertFalse((self.root / ".codex").exists())
        self.assertNotIn(install.BLOCK_START, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(pm.read_json(self.root / "memory/automation.json")["adapters"], ["claude-code"])
        before = self.snapshot()
        self.assertEqual({a["action"] for a in self.setup(apply=True, project_id="demo", clients=("claude-code",))["actions"]}, {"unchanged"})
        self.assertEqual(before, self.snapshot())
        stop = merged["hooks"]["Stop"][1]["hooks"][0]
        argv = [stop["command"], *(arg.replace("${CLAUDE_PROJECT_DIR}", str(self.root)) for arg in stop["args"])]
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s", "prompt_id": "p", "stop_hook_active": False, "last_assistant_message": "Done."})
        run = subprocess.run(argv, input=payload.encode(), capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual((run.returncode, json.loads(run.stdout)), (0, {}))
        self.assertEqual(install.uninstall(self.root, apply=True)["exit"], 0)
        self.assertEqual((self.root / ".claude/settings.local.json").read_bytes(), local)
        self.assertEqual((self.root / ".claude/settings.json").read_bytes(), shared)
        self.assertEqual((self.root / "CLAUDE.md").read_bytes(), claude_md)

    def test_both_clients_share_one_binding_and_manifest(self):
        self.setup(apply=True, project_id="demo")
        claude = self.setup(apply=True, clients=("claude-code",))
        self.assertEqual(claude["exit"], 0)
        self.assertEqual(pm.read_json(self.root / "memory/automation.json")["adapters"], ["claude-code", "codex"])
        self.assertEqual(sorted(pm.read_json(self.root / "memory/automation/install.json")["clients"]), ["claude-code", "codex"])
        self.assertEqual((self.root / ".claude/.gitignore").read_text(encoding="utf-8"), "settings.local.json\n")
        with patch.object(install, "claude_version", return_value=None):
            missing = self.setup(apply=True, clients=("claude-code",))
        self.assertEqual(missing["exit"], 4)
        self.assertTrue(any("Claude Code" in step for step in missing["next_steps"]))
        install.uninstall(self.root, apply=True)
        for path in (".codex", ".claude", "CLAUDE.md", "memory/automation.json", "memory/automation/install.json"):
            self.assertFalse((self.root / path).exists(), path)
        self.assertNotIn(install.BLOCK_START, (self.root / "AGENTS.md").read_text(encoding="utf-8"))


    def test_manifest_uses_command_sha256_and_still_reads_the_old_key(self):
        self.setup(apply=True)
        record = pm.read_json(self.root / "memory/automation/install.json")["clients"]["codex"]
        self.assertIn("command_sha256", record)
        self.assertNotIn("hook_sha256", record)
        self.assertEqual(install.command_digest(record), record["command_sha256"])
        self.assertEqual(install.command_digest({"hook_sha256": "a" * 64}), "a" * 64)


    def test_generated_hook_command_runs_from_the_system_shell(self):
        self.setup(apply=True)
        command = self.hooks()["hooks"]["Stop"][0]["hooks"][0]["command"]
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s-1", "turn_id": "t-1", "stop_hook_active": False, "last_assistant_message": "Done."})
        run = subprocess.run(command, shell=True, input=payload.encode("utf-8"), capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), {})
        self.assertEqual(len(list((self.root / "memory/automation/receipts").glob("*.json"))), 1)


    def test_setup_dry_run_in_fresh_repository_reads_block_from_package(self):
        with tempfile.TemporaryDirectory(prefix="fresh-repo-") as folder:
            target = Path(folder) / "fresh-project"
            target.mkdir()
            (target / ".git").mkdir()
            plan = install.setup(target, apply=False)
            self.assertEqual((plan["exit"], plan["applied"]), (5, False))
            self.assertTrue(any("missing" in c.lower() for c in plan["conflicts"]))
            self.assertEqual({a["path"]: a["action"] for a in plan["actions"]},
                             {"memory/automation.json": "create", ".codex/hooks.json": "create", ".codex/.gitignore": "create", "AGENTS.md": "create", "memory/automation/install.json": "create"})

    def test_setup_apply_refuses_missing_runtime_assets_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="missing-assets-") as folder:
            target = Path(folder).resolve()
            owner = target / "AGENTS.md"
            owner.write_bytes(b"# Owner rules\r\nKeep these bytes.")
            before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            result = install.setup(target, apply=True)
            self.assertEqual((result["exit"], result["applied"]), (5, False))
            self.assertTrue(any("adapters/codex/hook.py" in c for c in result["conflicts"]))
            self.assertEqual(before, {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()})

    def test_setup_refuses_each_missing_selected_runtime_prerequisite(self):
        for relative in ("scripts/dreamdocs.py", "scripts/memory_capture.py", "adapters/codex/hook.py", "memory/config.json", "templates/outcome-event.schema.json"):
            with self.subTest(path=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                try:
                    before = self.snapshot()
                    result = self.setup(apply=True)
                    self.assertEqual((result["exit"], result["applied"]), (5, False))
                    self.assertEqual(before, self.snapshot())
                finally:
                    path.write_bytes(original)

    def test_setup_refuses_empty_or_incomplete_target_outcome_block(self):
        path = self.root / install.BLOCK_FILE
        for block in ("", install.BLOCK_START + "\nIncomplete owner block\n"):
            with self.subTest(block=block):
                path.write_text(block, encoding="utf-8")
                before = self.snapshot()
                result = self.setup(apply=True)
                self.assertEqual((result["exit"], result["applied"]), (5, False))
                self.assertEqual(before, self.snapshot())

    def test_setup_preserves_valid_target_outcome_block(self):
        custom = install.BLOCK_START + "\nReviewed owner outcome instructions.\n" + install.BLOCK_END + "\n"
        (self.root / install.BLOCK_FILE).write_text(custom, encoding="utf-8")
        result = self.setup(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (0, True))
        self.assertIn(custom, (self.root / "AGENTS.md").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()

