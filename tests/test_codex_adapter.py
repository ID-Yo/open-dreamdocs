import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import project_memory as pm

FIXTURES = ROOT / "tests/fixtures/codex"
SECRET = "BEGIN PRIVATE KEY"


def block(**outcome):
    return "Work finished.\n\n```dreamdocs-outcome\n" + json.dumps(outcome) + "\n```\n"


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-adapter-")
        self.root = Path(self.temp.name).resolve() / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "example-project", "adapters": ["codex"]}), encoding="utf-8")
        (self.root / "docs/note.md").write_text("note\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, name, **changes):
        value = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        value["cwd"] = str(self.root)
        value.update(changes)
        return value

    def hook(self, value, raw=None):
        run = subprocess.run([sys.executable, "-B", str(self.root / "adapters/codex/hook.py")], input=(raw if raw is not None else json.dumps(value)).encode("utf-8"),
                             capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = run.stdout.decode("utf-8").strip()
        return json.loads(out) if out else None

    def files(self, folder):
        path = self.root / folder
        return sorted(p.name for p in path.glob("*") if p.name != "README.md") if path.is_dir() else []

    def all_text(self):
        return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (self.root / "memory").rglob("*") if p.is_file())

    def test_stop_with_outcome_block_saves_episode_then_session_start_recalls_it(self):
        message = block(status="success", summary="Stabilized the deploy test.", lessons=["The recall marker for this project is RECALL-7Q."], evidence=["file:docs/note.md"], task={"id": "task-7", "status": "done"})
        self.assertEqual(self.hook(self.payload("stop", last_assistant_message=message)), {})
        episodes = self.files("memory/episodes")
        self.assertEqual(len(episodes), 1)
        text = (self.root / "memory/episodes" / episodes[0]).read_text(encoding="utf-8")
        self.assertIn("RECALL-7Q", text)
        self.assertIn("task-7, reported done", text)
        self.assertEqual(self.files("memory/automation/events"), [])
        self.assertEqual(len(self.files("memory/automation/receipts")), 1)
        out = self.hook(self.payload("session_start"))
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("RECALL-7Q", context)
        self.assertIn("untrusted", context)
        self.assertEqual(self.hook(self.payload("stop", last_assistant_message=message)), {})
        self.assertEqual(len(self.files("memory/episodes")), 1)

    def test_stop_without_block_records_receipt_only_and_stores_no_assistant_text(self):
        self.assertEqual(self.hook(self.payload("stop", last_assistant_message="Private answer text MARK-3141.")), {})
        self.assertEqual(self.files("memory/episodes"), [])
        receipts = self.files("memory/automation/receipts")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(pm.read_json(self.root / "memory/automation/receipts" / receipts[0])["outcome"], "no_lesson")
        self.assertNotIn("MARK-3141", self.all_text())

    def test_stop_hook_active_and_garbage_input_never_block(self):
        self.assertEqual(self.hook(self.payload("stop", stop_hook_active=True, last_assistant_message=block(status="success", summary="x", lessons=[], evidence=["ref:a"]))), {})
        self.assertEqual(self.files("memory/automation/receipts"), [])
        self.assertIsNone(self.hook(None, raw="not json"))
        self.assertIsInstance(self.hook(None, raw='{"hook_event_name": "Stop", "session_id": 5}'), dict)

    def test_invalid_block_falls_back_to_receipt_with_warning(self):
        message = "Done.\n```dreamdocs-outcome\n{not json\n```\n"
        out = self.hook(self.payload("stop", last_assistant_message=message))
        self.assertIn("outcome block", out["systemMessage"])
        self.assertEqual(self.files("memory/episodes"), [])
        self.assertEqual(len(self.files("memory/automation/receipts")), 1)

    def test_unsafe_block_writes_nothing_and_echoes_nothing(self):
        message = block(status="success", summary=f"Pasted -----{SECRET}----- here.", lessons=[], evidence=["ref:a"])
        out = self.hook(self.payload("stop", last_assistant_message=message))
        self.assertIn("reject", out["systemMessage"])
        self.assertNotIn(SECRET, json.dumps(out))
        self.assertEqual((self.files("memory/automation/events"), self.files("memory/automation/receipts"), self.files("memory/episodes")), ([], [], []))
        self.assertNotIn(SECRET, self.all_text())

    def test_prompt_recall_only_for_meaningful_prompts(self):
        self.hook(self.payload("stop", last_assistant_message=block(status="success", summary="Deploy test fixed.", lessons=["Deploy tests need the build cache."], evidence=["ref:a"])))
        self.assertIsNone(self.hook(self.payload("user_prompt_submit", prompt="ok thanks")))
        out = self.hook(self.payload("user_prompt_submit"))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("build cache", out["hookSpecificOutput"]["additionalContext"])

    def test_busy_lock_queues_at_stop_and_session_end_publishes(self):
        lock = self.root / "memory/dreamer/command.lock"
        lock.write_text("live writer", encoding="utf-8")
        out = self.hook(self.payload("stop", last_assistant_message=block(status="success", summary="Queued work.", lessons=[], evidence=["ref:a"])))
        self.assertIn("queued", out["systemMessage"])
        lock.unlink()
        self.assertIsNone(self.hook(self.payload("session_end")))
        self.assertEqual((len(self.files("memory/episodes")), self.files("memory/automation/pending")), (1, []))

    def test_missing_binding_is_reported_without_blocking(self):
        (self.root / "memory/automation.json").unlink()
        self.assertIn("not installed", self.hook(self.payload("stop", last_assistant_message="Done."))["systemMessage"])
        self.assertIsNone(self.hook(self.payload("session_start")))
        self.assertEqual(self.files("memory/automation/receipts"), [])


if __name__ == "__main__":
    unittest.main()

