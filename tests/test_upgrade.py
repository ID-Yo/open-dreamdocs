import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
import memory_capture as mc
import project_memory as pm
import upgrade

LEGACY = "26c7aff57be6ffb4ccd6287c979e3782a0a19b2a"
EVENT = json.loads((ROOT / "tests/fixtures/automation/success-capture.json").read_text(encoding="utf-8"))["event"]


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dreamdocs-upgrade-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "custom project"
        self.source = Path(self.temp.name) / "reviewed package"
        for folder in (self.root, self.source):
            for p in pm.managed_files(ROOT):
                target = folder / p.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, target)
        self.addCleanup(patch.stopall)
        patch.object(install, "codex_version", return_value="0.147.0").start()
        patch.object(install, "claude_version", return_value="2.1.273").start()
        install.setup(self.root, True, "example-project", ("codex", "claude-code"))
        asset = self.source / "scripts/human_materials.py"
        asset.write_bytes(asset.read_bytes() + b"\n# selected reviewed release\n")
        version_file = self.source / "scripts/install.py"
        version_file.write_bytes(version_file.read_bytes().replace(('PACKAGE_VERSION = "' + install.PACKAGE_VERSION + '"').encode(), b'PACKAGE_VERSION = "automation-fixture-v2"', 1))
        self.release()

    def release(self):
        manifest = {"version": 1, "upstream": upgrade.UPSTREAM, "revision": "a" * 40, "package_version": "automation-fixture-v2",
                    "memory_schema": 1, "files": {p.relative_to(self.source).as_posix(): pm.digest(p.read_bytes())
                    for p in self.source.rglob("*") if p.is_file() and upgrade.package_asset(p.relative_to(self.source).as_posix())}}
        path = self.source / "dreamdocs-release.json"
        pm.atomic(path, manifest)
        self.pin = pm.digest(path.read_bytes())

    def run_upgrade(self, **kwargs):
        return upgrade.update(self.root, self.source, self.pin, "a" * 40, **kwargs)

    def snapshot(self, root=None):
        folder = root or self.root
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}

    def test_dry_run_classifies_without_writes_and_update_preserves_user_data(self):
        doc = self.root / "docs/status/current-state.md"
        doc.write_bytes(b"owner customized status\r\n")
        mc.capture(self.root, copy.deepcopy(EVENT))
        before = self.snapshot()
        plan = self.run_upgrade()
        self.assertFalse(plan["applied"])
        self.assertEqual(before, self.snapshot())
        self.assertIn("update", {a["action"] for a in plan["actions"]})
        result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (0, True))
        for path, data in before.items():
            if path.startswith(("docs/", "human-materials/", "memory/episodes/", "memory/automation/receipts/")):
                self.assertEqual((self.root / path).read_bytes(), data, path)
        self.assertEqual(pm.read_json(self.root / install.MANIFEST)["clients"]["codex"]["trust"], "pending")
        self.assertEqual(self.run_upgrade(apply=True)["state"], "unchanged")

    def test_project_files_recorded_by_older_setup_are_kept_and_not_blockers(self):
        manifest = pm.read_json(self.root / install.MANIFEST)
        own = {"scripts/deploy.ps1": b"Write-Host deploy\n", "scripts/project_tool.py": b"print('project')\n"}
        for path, data in own.items():
            (self.root / path).write_bytes(data)
            manifest["package_files"][path] = pm.digest(data)  # what rc.1/rc.2 setup recorded
        pm.atomic(self.root / install.MANIFEST, manifest)
        result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (0, True), result.get("conflicts"))
        for path, data in own.items():
            self.assertEqual((self.root / path).read_bytes(), data)
        self.assertNotIn("scripts/deploy.ps1", pm.read_json(self.root / install.MANIFEST)["package_files"])

    def test_modified_package_unknown_collisions_and_changed_instruction_block_refuse_all_writes(self):
        asset = self.root / "scripts/human_materials.py"
        asset.write_bytes(asset.read_bytes() + b"\n# owner edit\n")
        before = self.snapshot()
        result = self.run_upgrade(apply=True)
        self.assertEqual(result["exit"], 5)
        self.assertEqual(before, self.snapshot())
        self.assertIn("scripts/human_materials.py", {a["path"] for a in result["actions"] if a["action"] == "conflict"})

    def test_source_identity_and_file_hash_are_independent_requirements(self):
        before = self.snapshot()
        self.assertEqual(upgrade.update(self.root, self.source, "0" * 64, "a" * 40, apply=True)["exit"], 5)
        manifest = pm.read_json(self.source / "dreamdocs-release.json")
        manifest["upstream"] = "https://example.invalid/attacker"
        pm.atomic(self.source / "dreamdocs-release.json", manifest)
        self.pin = pm.digest((self.source / "dreamdocs-release.json").read_bytes())
        self.assertEqual(self.run_upgrade(apply=True)["exit"], 5)
        self.release()
        (self.source / "scripts/human_materials.py").write_bytes(b"tampered after pin")
        self.assertEqual(self.run_upgrade(apply=True)["exit"], 5)
        self.assertEqual(before, self.snapshot())

    def test_active_writer_and_unsupported_schema_fail_before_backups(self):
        lock = self.root / "memory/dreamer/command.lock"
        pm.atomic(lock, {"owner_pid": 1, "acquired_at": pm.now()})
        before = self.snapshot()
        self.assertEqual(self.run_upgrade(apply=True)["exit"], 5)
        self.assertEqual(before, self.snapshot())
        lock.unlink()
        cfg = pm.read_json(self.root / "memory/config.json")
        cfg["version"] = 99
        pm.atomic(self.root / "memory/config.json", cfg)
        before = self.snapshot()
        self.assertEqual(self.run_upgrade(apply=True)["exit"], 5)
        self.assertEqual(before, self.snapshot())

    def test_real_v140_archive_adoption_from_new_package_preserves_customized_docs(self):
        try:
            fixture = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", LEGACY + "^{commit}"], capture_output=True, timeout=10)
        except FileNotFoundError:
            self.skipTest("Legacy v1.4.0 Git fixture unavailable; full reviewed Git-source suite is required before release.")
        if fixture.returncode:
            self.skipTest("History-free package has no legacy v1.4.0 Git fixture; full reviewed Git-source suite remains required.")
        legacy = Path(self.temp.name) / "legacy"
        legacy.mkdir()
        archive = subprocess.run(["git", "archive", LEGACY], cwd=ROOT, capture_output=True, check=True, timeout=30).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(legacy, filter="data")
        self.root = legacy
        (legacy / "PROJECT.md").write_bytes(b"My adopted project\r\n")
        (legacy / "docs/status/current-state.md").write_bytes(b"custom current state\r\n")
        before = self.snapshot()
        self.assertFalse((legacy / "scripts/dreamdocs.py").exists())
        result = self.run_upgrade(apply=True, from_version="v1.4.0", clients=("codex", "claude-code"))
        self.assertEqual((result["exit"], result["applied"]), (0, True), result.get("conflicts"))
        for path, data in before.items():
            if path.startswith(("docs/", "memory/", "human-materials/")) or path == "PROJECT.md":
                self.assertEqual((legacy / path).read_bytes(), data, path)
        self.assertTrue((legacy / "scripts/dreamdocs.py").exists())
        self.assertTrue(pm.validate(legacy)["ok"])
        checked = subprocess.run([sys.executable, "-B", str(legacy / "scripts/project_memory.py"), "--root", str(legacy), "validate"], capture_output=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        owner_readme = legacy / "memory/automation/receipts/README.md"
        owner_readme.write_bytes(owner_readme.read_bytes() + b"\nOwner receipt retention notes must survive rollback.\n")
        new_event = copy.deepcopy(EVENT)
        new_event["project_id"] = pm.read_json(legacy / "memory/automation.json")["project_id"]
        mc.capture(legacy, new_event)
        captured = {p: data for p, data in self.snapshot().items() if p.startswith(("memory/episodes/", "memory/automation/receipts/"))}
        reverted = upgrade.rollback(legacy, result["backup"], apply=True)
        self.assertEqual(reverted["exit"], 0, reverted)
        self.assertIn("no automatic lifecycle adapters", reverted["compatibility"])
        self.assertFalse((legacy / "scripts/dreamdocs.py").exists())
        for path, data in captured.items():
            self.assertEqual((legacy / path).read_bytes(), data)
        self.assertTrue(pm.validate(legacy)["ok"])
        checked = subprocess.run([sys.executable, "-B", str(legacy / "scripts/project_memory.py"), "--root", str(legacy), "validate"], capture_output=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_upgrade_preserves_existing_user_runtime_readmes_and_validates_before_claiming_version(self):
        for name in ("memory/automation/README.md", "memory/automation/receipts/README.md"):
            (self.root / name).write_bytes(b"# Owner notes\n\nKeep these exact user notes.\n")
        result = self.run_upgrade(apply=True)
        self.assertEqual(result["exit"], 0, result)
        for name in ("memory/automation/README.md", "memory/automation/receipts/README.md"):
            self.assertEqual((self.root / name).read_bytes(), b"# Owner notes\n\nKeep these exact user notes.\n")
        self.assertTrue(pm.validate(self.root)["ok"])
        self.assertEqual(upgrade.rollback(self.root, result["backup"], apply=True)["exit"], 0)
        for name in ("memory/automation/README.md", "memory/automation/receipts/README.md"):
            self.assertEqual((self.root / name).read_bytes(), b"# Owner notes\n\nKeep these exact user notes.\n")

    def test_new_validator_failure_keeps_previous_installed_version_and_recoverable_journal(self):
        before = (self.root / install.MANIFEST).read_bytes()
        with patch.object(upgrade.pm, "validate_runtime", side_effect=pm.MemoryError("injected runtime validation failure")):
            result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (5, False))
        self.assertEqual((self.root / install.MANIFEST).read_bytes(), before)
        self.assertEqual(pm.read_json(self.root / result["backup"] / "journal.json")["state"], "interrupted")

    def test_project_documentation_style_never_blocks_upgrade_or_rollback(self):
        folder = self.root / "docs/engineering/proposals/rpt-usage-v1"
        folder.mkdir(parents=True)
        (folder / "design.md").write_text("Project-owned proposal without folder READMEs.\n", encoding="utf-8")
        with self.assertRaises(pm.MemoryError):
            pm.validate(self.root)
        result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (0, True), result.get("conflicts"))
        reverted = upgrade.rollback(self.root, result["backup"], apply=True)
        self.assertEqual(reverted["exit"], 0, reverted)
        self.assertEqual((folder / "design.md").read_text(encoding="utf-8"), "Project-owned proposal without folder READMEs.\n")

    def test_backup_negations_refuse_before_payload_publication_and_preserve_owner_rules(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        ignore = self.root / ".dreamdocs/.gitignore"
        ignore.parent.mkdir(parents=True, exist_ok=True)
        rules = b"*\n!backups/\n!backups/**\n"
        ignore.write_bytes(rules)
        before = self.snapshot()
        with patch.dict(install.TIMEOUTS, {"Stop": 99}):
            result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (5, False))
        self.assertFalse((self.root / ".dreamdocs/backups").exists())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(ignore.read_bytes(), rules)

    def test_effective_backup_exclusion_rechecks_under_lock_and_refuses_rollback_exposure(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        with patch.dict(install.TIMEOUTS, {"Stop": 99}):
            result = self.run_upgrade(apply=True)
        self.assertEqual(result["exit"], 0, result)
        listed = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", result["backup"]], cwd=self.root, capture_output=True, check=True, timeout=10)
        self.assertEqual(listed.stdout, b"")
        ignore = self.root / ".dreamdocs/.gitignore"
        ignore.write_bytes(b"*\n!backups/\n!backups/**\n")
        before = self.snapshot()
        reverted = upgrade.rollback(self.root, result["backup"], apply=True)
        self.assertEqual((reverted["exit"], reverted["applied"]), (5, False))
        self.assertEqual(self.snapshot(), before)

    def test_backup_index_and_unverifiable_git_refuse_but_non_git_remains_supported(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        original = upgrade.subprocess.run
        def tracked(argv, **kwargs):
            if argv[0] == "git" and "ls-files" in argv:
                return subprocess.CompletedProcess(argv, 0, b".dreamdocs/backups/transaction/journal.json\0", b"")
            return original(argv, **kwargs)
        for failure in (None, subprocess.TimeoutExpired("git", 5)):
            before = self.snapshot()
            with patch.object(upgrade.subprocess, "run", side_effect=tracked if failure is None else failure):
                result = self.run_upgrade(apply=True)
            self.assertEqual((result["exit"], result["applied"]), (5, False))
            self.assertEqual(self.snapshot(), before)

    def test_backup_ignore_change_between_plan_and_lock_refuses_before_private_payloads(self):
        from contextlib import contextmanager
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True, timeout=10)
        ignore = self.root / ".dreamdocs/.gitignore"
        ignore.parent.mkdir(parents=True, exist_ok=True); ignore.write_bytes(b"*\n")
        original = pm.operation
        @contextmanager
        def exposed(root):
            ignore.write_bytes(b"*\n!backups/\n!backups/**\n")
            with original(root):
                yield
        manifest = (self.root / install.MANIFEST).read_bytes()
        with patch.object(pm, "operation", side_effect=exposed):
            result = self.run_upgrade(apply=True)
        self.assertEqual((result["exit"], result["applied"]), (5, False))
        self.assertFalse((self.root / upgrade.BACKUPS).exists())
        self.assertEqual((self.root / install.MANIFEST).read_bytes(), manifest)

    def test_non_git_backup_remains_self_ignoring_without_requiring_git(self):
        original = upgrade.subprocess.run
        def no_git(argv, **kwargs):
            if argv[0] == "git":
                raise FileNotFoundError("Git intentionally unavailable in copied project")
            return original(argv, **kwargs)
        with patch.object(upgrade.subprocess, "run", side_effect=no_git):
            result = self.run_upgrade(apply=True)
            self.assertEqual(result["exit"], 0, result)
            self.assertEqual((self.root / result["backup"] / ".gitignore").read_bytes(), b"*\n")
            self.assertIn("future Git adoption", result["backup_privacy"])
            self.assertEqual(upgrade.rollback(self.root, result["backup"], apply=True)["exit"], 0)

    def test_new_zip_cli_upgrades_genuine_legacy_then_rolls_back_with_valid_new_memory_scaffold(self):
        fixture = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", LEGACY + "^{commit}"], capture_output=True, timeout=10)
        if fixture.returncode:
            self.skipTest("History-free package has no v1.4.0 archive fixture; full Git-source upgrade roundtrip remains required.")
        legacy = Path(self.temp.name) / "legacy-cli"
        legacy.mkdir()
        raw = subprocess.run(["git", "archive", LEGACY], cwd=ROOT, capture_output=True, check=True, timeout=30).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
            stream.extractall(legacy, filter="data")
        package = Path(self.temp.name) / "new-package.zip"
        with zipfile.ZipFile(package, "w") as archive:
            for path in self.source.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(self.source).as_posix())
        extracted = Path(self.temp.name) / "new-extracted"
        with zipfile.ZipFile(package) as archive:
            archive.extractall(extracted)
        (legacy / "scripts/README.md").write_bytes(b"# Owner script guidance\n\nKeep this customized guidance.\n")
        before_config = (legacy / "memory/config.json").read_bytes()
        def cli(*args):
            result = subprocess.run([sys.executable, "-B", str(extracted / "scripts/dreamdocs.py"), "--root", str(legacy), *args], capture_output=True, timeout=60)
            return result.returncode, json.loads(result.stdout)
        code, applied = cli("upgrade", "--source", str(extracted), "--revision", "a" * 40, "--manifest-sha256", self.pin,
                            "--from-version", "v1.4.0", "--client", "codex", "--apply")
        self.assertEqual(code, 0, applied)
        self.assertTrue(applied["applied"])
        self.assertEqual((legacy / "scripts/README.md").read_bytes(), b"# Owner script guidance\n\nKeep this customized guidance.\n")
        for phase in ("upgraded", "rolled_back"):
            checked = subprocess.run([sys.executable, "-B", str(legacy / "scripts/project_memory.py"), "--root", str(legacy), "validate"], capture_output=True, timeout=30)
            self.assertEqual(checked.returncode, 0, (phase, checked.stderr))
            if phase == "upgraded":
                event = copy.deepcopy(EVENT)
                event["project_id"] = pm.read_json(legacy / "memory/automation.json")["project_id"]
                self.assertTrue(mc.capture(legacy, event)["saved"])
                notes = legacy / "memory/automation/README.md"
                notes.write_bytes(notes.read_bytes() + b"\nOwner notes created after upgrade.\n")
                code, reverted = cli("rollback", "--backup", applied["backup"], "--apply")
                self.assertEqual(code, 0, reverted)
        self.assertIn(b"Owner notes created after upgrade", (legacy / "memory/automation/README.md").read_bytes())
        self.assertTrue(list((legacy / "memory/automation/receipts").glob("*.json")))
        self.assertTrue(list((legacy / "memory/episodes").glob("auto-*.md")))
        self.assertEqual((legacy / "memory/config.json").read_bytes(), before_config)

    def test_no_space_or_write_failure_leaves_recoverable_journal_without_claiming_version(self):
        before_manifest = (self.root / install.MANIFEST).read_bytes()
        with patch.object(upgrade.shutil, "disk_usage", return_value=shutil._ntuple_diskusage(100, 99, 1)):
            self.assertEqual(self.run_upgrade(apply=True)["exit"], 5)
        self.assertEqual((self.root / install.MANIFEST).read_bytes(), before_manifest)
        original = upgrade.atomic_bytes
        def fail(path, data):
            if path == self.root / "scripts/human_materials.py":
                raise PermissionError("injected target write denial")
            original(path, data)
        with patch.object(upgrade, "atomic_bytes", side_effect=fail):
            failed = self.run_upgrade(apply=True)
        self.assertEqual(failed["exit"], 5)
        self.assertEqual((self.root / install.MANIFEST).read_bytes(), before_manifest)
        self.assertEqual(pm.read_json(self.root / failed["backup"] / "journal.json")["state"], "interrupted")

    def test_rollback_between_automation_versions_preserves_new_memory_and_exact_package_bytes(self):
        before = self.snapshot()
        applied = self.run_upgrade(apply=True)
        new_event = copy.deepcopy(EVENT)
        new_event["turn_id"] = "after-upgrade"
        mc.capture(self.root, new_event)
        memory = {p: data for p, data in self.snapshot().items() if p.startswith(("memory/episodes/", "memory/automation/receipts/"))}
        result = upgrade.rollback(self.root, applied["backup"], apply=True)
        self.assertEqual((result["exit"], result["applied"]), (0, True), result)
        for path, data in before.items():
            if not path.startswith(".dreamdocs/"):
                self.assertEqual((self.root / path).read_bytes(), data, path)
        for path, data in memory.items():
            self.assertEqual((self.root / path).read_bytes(), data)
        self.assertIn("requires real client probes", result["compatibility"])
        for adapter, turn_key in (("codex", "turn_id"), ("claude-code", "prompt_id")):
            message = '```dreamdocs-outcome\n' + json.dumps({"summary": "Post rollback fixture marker ROLLBACK-C9", "lessons": ["Marker ROLLBACK-C9"], "evidence": ["ref:fixture"]}) + '\n```'
            payload = {"hook_event_name": "Stop", "session_id": adapter + "-rollback-save", turn_key: "new-turn", "last_assistant_message": message}
            hook = self.root / f"adapters/{adapter}/hook.py"
            run = subprocess.run([sys.executable, "-B", str(hook)], input=json.dumps(payload).encode(), capture_output=True, timeout=30)
            self.assertEqual((run.returncode, json.loads(run.stdout)), (0, {}))
            recall = subprocess.run([sys.executable, "-B", str(hook)], input=json.dumps({"hook_event_name": "SessionStart", "session_id": "fresh"}).encode(), capture_output=True, timeout=30)
            self.assertIn("ROLLBACK-C9", json.loads(recall.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_rollback_refuses_post_upgrade_package_or_instruction_edits(self):
        applied = self.run_upgrade(apply=True)
        path = self.root / "scripts/human_materials.py"
        path.write_bytes(path.read_bytes() + b"\n# new owner edit\n")
        before = self.snapshot()
        result = upgrade.rollback(self.root, applied["backup"], apply=True)
        self.assertEqual(result["exit"], 5)
        self.assertEqual(before, self.snapshot())

    def test_interrupted_update_can_rollback_without_touching_later_memory(self):
        original = upgrade.atomic_bytes
        def fail(path, data):
            if path == self.root / "scripts/human_materials.py":
                raise OSError("injected interruption")
            original(path, data)
        before = self.snapshot()
        with patch.object(upgrade, "atomic_bytes", side_effect=fail):
            failed = self.run_upgrade(apply=True)
        self.assertEqual(failed["exit"], 5)
        recovered = upgrade.rollback(self.root, failed["backup"], apply=True)
        self.assertEqual(recovered["exit"], 0, recovered)
        for path, data in before.items():
            if not path.startswith(".dreamdocs/"):
                self.assertEqual((self.root / path).read_bytes(), data, path)


if __name__ == "__main__":
    unittest.main()
