import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import docs_status as ds
import project_memory as pm

FIXTURES = ROOT / "tests/fixtures/codex"


def block(**outcome):
    return "Done.\n\n```dreamdocs-outcome\n" + json.dumps(outcome) + "\n```\n"


class DocsStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="docs-status-")
        self.root = Path(self.temp.name).resolve() / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "example-project", "adapters": ["codex"]}), encoding="utf-8")
        (self.root / "docs/note.md").write_text("note\n", encoding="utf-8")
        self.turn = 0

    def tearDown(self):
        self.temp.cleanup()

    def hook(self, name, **changes):
        value = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        value["cwd"] = str(self.root)
        value.update(changes)
        run = subprocess.run([sys.executable, "-B", str(self.root / "adapters/codex/hook.py")], input=json.dumps(value).encode("utf-8"),
                             capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = run.stdout.decode("utf-8").strip()
        return json.loads(out) if out else None

    def stop(self, **outcome):
        self.turn += 1
        outcome.setdefault("status", "success")
        outcome.setdefault("evidence", ["file:docs/note.md"])
        return self.hook("stop", turn_id=f"turn-{self.turn}", last_assistant_message=block(**outcome))

    def read(self, relative):
        return (self.root / relative).read_bytes().decode("utf-8")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_stop_appends_activity_and_refreshes_status_block_once(self):
        owner_text = self.read(ds.STATE_PAGE)
        self.assertEqual(self.stop(summary="Shipped the deploy check.", task={"id": "TASK-7", "status": "review"}), {})
        log = self.read(ds.LOG)
        self.assertEqual(len(ds.logged(log)), 1)
        self.assertIn("· success · [TASK-7: review] · Shipped the deploy check. Evidence: `file:docs/note.md`.", log)
        page = self.read(ds.STATE_PAGE)
        self.assertTrue(page.startswith(owner_text.rstrip("\n")), "owner text before the block must stay unchanged")
        self.assertIn("### Open tasks (latest reported status)", page)
        self.assertIn("- TASK-7: review", page)
        self.assertEqual(self.hook("stop", turn_id=f"turn-{self.turn}", last_assistant_message=block(status="success", summary="Shipped the deploy check.", evidence=["file:docs/note.md"], task={"id": "TASK-7", "status": "review"})), {})
        self.assertEqual(self.read(ds.LOG), log, "a redelivered turn must not add a second line")
        self.stop(summary="Closed it.", task={"id": "TASK-7", "status": "done"})
        page = self.read(ds.STATE_PAGE)
        self.assertNotIn("- TASK-7: review", page)
        self.assertEqual(page.count(ds.START), 1)
        self.assertEqual(pm.validate(self.root)["ok"], True)

    def test_no_lesson_turns_and_disabled_projects_write_no_docs(self):
        self.hook("stop", turn_id="plain", last_assistant_message="Just an answer.")
        self.assertFalse((self.root / ds.LOG).exists())
        (self.root / ".dreamdocs").mkdir(exist_ok=True)
        (self.root / ds.SETTINGS).write_text('{"automatic_status": false}', encoding="utf-8")
        before = self.read(ds.STATE_PAGE)
        self.stop(summary="Saved but docs are off.")
        self.assertFalse((self.root / ds.LOG).exists())
        self.assertEqual(self.read(ds.STATE_PAGE), before)

    def test_crlf_owner_page_keeps_every_byte_outside_the_markers(self):
        page = self.root / ds.STATE_PAGE
        original = b"# Current State\r\n\r\nOwner line one.\r\n\r\n## Next\r\n- keep me\r\n"
        page.write_bytes(original)
        self.stop(summary="First.")
        first = page.read_bytes()
        self.assertTrue(first.startswith(original.rstrip(b"\r\n")))
        self.assertNotIn(b"\n", first.replace(b"\r\n", b""), "the page keeps CRLF line endings")
        edited = first.replace(b"Owner line one.", b"Owner line edited.")
        page.write_bytes(edited)
        self.stop(summary="Second.")
        second = page.read_bytes()
        head = edited.split(ds.START.encode())[0]
        self.assertTrue(second.startswith(head))
        self.assertIn(b"Second.", second)

    def test_incomplete_markers_are_refused_and_reported(self):
        page = self.root / ds.STATE_PAGE
        page.write_text("# Current State\n\n" + ds.START + "\nhalf\n", encoding="utf-8")
        before = page.read_bytes()
        result = self.stop(summary="Marker test.")
        self.assertIn("current-state markers are incomplete", result["systemMessage"])
        self.assertEqual(page.read_bytes(), before)
        self.assertEqual(len(ds.logged(self.read(ds.LOG))), 1, "the log is still written")

    def test_outcomes_saved_while_docs_were_deferred_are_caught_up_at_session_start(self):
        lock = self.root / "memory/dreamer/command.lock"
        lock.write_text("live writer", encoding="utf-8")
        self.stop(summary="Queued while busy.")
        lock.unlink()
        self.assertFalse((self.root / ds.LOG).exists())
        self.hook("session_start")
        self.assertIn("Queued while busy.", self.read(ds.LOG))

    def test_code_without_docs_is_docs_debt_until_docs_change(self):
        self.git("init", "-q")
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "base")
        (self.root / "app.py").write_text("print(1)\n", encoding="utf-8")
        self.stop(summary="Added the app.")
        state = ds.load_debt(self.root)
        self.assertEqual(state["files"], ["app.py"])
        start = self.hook("session_start")
        self.assertIn("Docs debt: 1 changed code file(s)", json.dumps(start))
        (self.root / "docs/note.md").write_text("note\nupdated\n", encoding="utf-8")
        self.stop(summary="Documented the app.")
        self.assertEqual(ds.load_debt(self.root)["files"], [])
        (self.root / "tool.py").write_text("print(2)\n", encoding="utf-8")
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "add", "-A")
        self.git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "work")
        self.stop(summary="Internal refactor.", docs_impact="none")
        self.assertEqual(ds.load_debt(self.root)["files"], [])
        (self.root / "other.py").write_text("print(3)\n", encoding="utf-8")
        self.stop(summary="Another change.")
        self.assertIn("other.py", ds.load_debt(self.root)["files"])

    def test_unsaved_events_are_named_at_session_start(self):
        folder = self.root / "memory/automation/events"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "evt-0000.json").write_text("{not json", encoding="utf-8")
        start = self.hook("session_start")
        self.assertIn("1 earlier turn outcome(s) are not saved yet", json.dumps(start))


if __name__ == "__main__":
    unittest.main()

