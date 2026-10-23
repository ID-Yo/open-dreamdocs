import copy
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

EVENT = json.loads((ROOT / "tests/fixtures/automation/success-capture.json").read_text(encoding="utf-8"))["event"]
TEXT = "Кирилица café \U0001F680 line\u2028separator"


class ConsoleEncodingTests(unittest.TestCase):
    """Machine output must survive a non-UTF-8 Windows console code page."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="encoding-test-")
        self.root = Path(self.temp.name).resolve() / "project"
        for path in pm.managed_files(ROOT):
            target = self.root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (self.root / "memory/automation.json").write_text(json.dumps({"version": 1, "project_id": "example-project", "adapters": ["codex"]}), encoding="utf-8")
        meta = {"id": "fact-unicode", "type": "semantic", "status": "active", "project": "example-project", "scope": "build",
                "created_at": "2026-01-01T00:00:00Z", "source": ["ref:x"], "owner": "owner", "accepted_by": "owner", "last_verified": "2026-01-02T00:00:00Z"}
        (self.root / "memory/facts/fact-unicode.md").write_text("---\n" + json.dumps(meta) + "\n---\n\n" + TEXT + "\n", encoding="utf-8")
        self.env = {**os.environ, "PYTHONIOENCODING": "cp1251"}

    def tearDown(self):
        self.temp.cleanup()

    def run_json(self, args, stdin=None):
        run = subprocess.run([sys.executable, "-B", *args], input=stdin, capture_output=True, env=self.env, timeout=60)
        self.assertNotIn(b"Traceback", run.stderr, run.stderr.decode("cp1251", errors="replace"))
        return run.returncode, json.loads(run.stdout.decode("ascii"))

    def test_recall_capture_checker_and_hook_emit_ascii_json(self):
        code, recalled = self.run_json([str(self.root / "scripts/dreamdocs.py"), "--root", str(self.root), "memory", "recall"])
        self.assertEqual((code, recalled["status"]), (0, "ok"))
        self.assertIn("Кирилица café \U0001F680", recalled["context"])
        event = copy.deepcopy(EVENT)
        event["outcome"]["summary"] = TEXT
        path = self.root / "event.json"
        path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
        code, checked = self.run_json([str(self.root / "scripts/automation_contract.py"), "--root", str(self.root), "--event", str(path)])
        self.assertEqual(checked["decision"], "capture_episode")
        code, captured = self.run_json([str(self.root / "scripts/dreamdocs.py"), "--root", str(self.root), "memory", "capture", "--event", str(path)])
        self.assertEqual((code, captured["saved"]), (0, True))
        payload = json.dumps({"hook_event_name": "SessionStart", "session_id": "s", "source": "startup"}).encode()
        code, hook = self.run_json([str(self.root / "adapters/codex/hook.py")], stdin=payload)
        self.assertEqual(code, 0)
        self.assertIn("Кирилица", hook["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()

