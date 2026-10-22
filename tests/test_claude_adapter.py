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
import project_memory as pm

FIXTURES = ROOT / "tests/fixtures/claude-code"


def block(**outcome):
    return "Finished.\n\n```dreamdocs-outcome\n" + json.dumps(outcome) + "\n```\n"


class ClaudeAdapterTests(unittest.TestCase):
    """Documented Claude Code 2.1.273 payloads; not yet observed with an authenticated session."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-adapter-")
        self.root = Path(self.temp.name).resolve() / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "example-project", "adapters": ["claude-code"]}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, name, **changes):
        value = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        value["cwd"] = str(self.root)
        value.update(changes)
        return {k: v for k, v in value.items() if v is not None}

    def hook(self, value):
        run = subprocess.run([sys.executable, "-B", str(self.root / "adapters/claude-code/hook.py")], input=json.dumps(value).encode("utf-8"),
                             capture_output=True, cwd=self.root, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = run.stdout.decode("ascii").strip()
        return json.loads(out) if out else None

    def files(self, folder):
        path = self.root / folder
        return sorted(p.name for p in path.glob("*") if p.name != "README.md") if path.is_dir() else []

    def test_stop_saves_by_prompt_id_and_session_start_recalls_it(self):
        message = block(status="success", summary="Stabilized deploy.", lessons=["Claude marker RECALL-C9."], evidence=["ref:pr-1"])
        self.assertEqual(self.hook(self.payload("stop", last_assistant_message=message)), {})
        self.assertEqual(self.hook(self.payload("stop", last_assistant_message=message)), {})
        [episode] = self.files("memory/episodes")
        self.assertIn('"ref:claude-code/' + self.payload("stop")["session_id"] + '/prompt-0001"', (self.root / "memory/episodes" / episode).read_text(encoding="utf-8"))
        out = self.hook(self.payload("session_start"))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("RECALL-C9", out["hookSpecificOutput"]["additionalContext"])

    def test_without_prompt_id_the_turn_is_keyed_by_the_final_message(self):
        for message in ("First answer.", "Second answer.", "First answer."):
            self.assertEqual(self.hook(self.payload("stop", prompt_id=None, last_assistant_message=message)), {})
        self.assertEqual(len(self.files("memory/automation/receipts")), 2)

    def test_stop_failure_is_interrupted_and_writes_nothing(self):
        self.assertIsNone(self.hook(self.payload("stop_failure")))
        self.assertEqual((self.files("memory/automation/receipts"), self.files("memory/automation/events"), self.files("memory/episodes")), ([], [], []))

    def test_stop_hook_active_prompt_recall_and_session_end(self):
        self.assertEqual(self.hook(self.payload("stop", stop_hook_active=True, last_assistant_message=block(status="success", summary="x", lessons=[], evidence=["ref:a"]))), {})
        self.assertEqual(self.files("memory/automation/receipts"), [])
        lock = self.root / "memory/dreamer/command.lock"
        lock.write_text("live writer", encoding="utf-8")
        queued = self.hook(self.payload("stop", last_assistant_message=block(status="success", summary="Deploy cache fixed.", lessons=["Deploy tests need the build cache."], evidence=["ref:a"])))
        self.assertIn("queued", queued["systemMessage"])
        lock.unlink()
        self.assertIsNone(self.hook(self.payload("session_end")))
        out = self.hook(self.payload("user_prompt_submit"))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("build cache", out["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()

