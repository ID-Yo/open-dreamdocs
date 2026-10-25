import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dreamer_schedule as ds  # noqa: E402
import human_materials as hm  # noqa: E402
import materials_index as mi  # noqa: E402
import memory_recall as mr  # noqa: E402


def summary(text="Planning notes for the spring launch with budget and owners.", category="notes"):
    return {"summary": text, "tags": ["Launch", "budget"], "category": category, "sensitivity": "internal",
            "read_original_when": "Exact figures or wording are needed."}


class Runner:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, prompt, image, timeout):
        self.calls.append(prompt)
        if self.fail:
            raise ValueError("Codex summarizer failed")
        return summary()


class MaterialsIndexTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "memory").mkdir()
        (self.root / "human-materials").mkdir()
        shutil.copy(ROOT / "human-materials" / "README.md", self.root / "human-materials" / "README.md")
        self.mode("inventory")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def mode(self, value, **extra):
        cfg = {"version": 1, "schedule": {"frequency": "daily", "timezone": None, "local_time": None, "owner": None},
               "review": {"episode_days": None}, "human_materials": {"indexing": value, **extra}}
        (self.root / "memory" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def put(self, relative, data):
        path = self.root / "human-materials" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def rows(self):
        return {r["path"]: r for r in hm.inventory(self.root)["rows"]}

    def test_off_reads_and_writes_nothing(self):
        self.mode("off")
        self.put("a.txt", "hello")
        before = (self.root / "human-materials" / "README.md").read_bytes()
        result = mi.index(self.root, True, runner=Runner())
        self.assertEqual(result["state"], "off")
        self.assertEqual((self.root / "human-materials" / "README.md").read_bytes(), before)
        self.assertFalse((self.root / mi.STATE).exists())

    def test_inventory_adds_moves_and_removes_rows_without_touching_originals(self):
        original = self.put("deck one.txt", "launch plan")
        runner = Runner()
        mi.index(self.root, True, runner=runner)
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.rows()["deck one.txt"]["status"], "unread")
        self.assertEqual(hm.check(self.root), [])
        moved = self.root / "human-materials" / "archive" / "deck one.txt"
        moved.parent.mkdir()
        original.replace(moved)
        result = mi.scan(self.root, True)
        self.assertEqual(result["moved"], {"deck one.txt": "archive/deck one.txt"})
        self.assertEqual(list(self.rows()), ["archive/deck one.txt"])
        self.assertEqual(moved.read_text(encoding="utf-8"), "launch plan")
        moved.unlink()
        mi.scan(self.root, True)
        self.assertEqual(self.rows(), {})
        self.assertEqual(hm.check(self.root), [])

    def test_summarize_writes_ai_draft_and_requeues_only_on_change(self):
        self.mode("summarize")
        path = self.put("plan.md", "Spring launch plan with budget.")
        runner = Runner()
        result = mi.index(self.root, True, runner=runner)
        self.assertEqual(result["summarized"], ["plan.md"])
        row = self.rows()["plan.md"]
        self.assertEqual(row["status"], "ai-draft")
        self.assertIn("category:notes", row["text"])
        self.assertIn("sensitivity:internal", row["text"])
        self.assertEqual(hm.check(self.root), [])
        mi.index(self.root, True, runner=runner)
        self.assertEqual(len(runner.calls), 1)
        path.write_text("Changed plan.", encoding="utf-8")
        mi.index(self.root, True, runner=runner)
        self.assertEqual(len(runner.calls), 2)

    def test_human_reviewed_row_is_kept_and_new_summary_is_a_proposal(self):
        self.mode("summarize")
        path = self.put("contract.txt", "v1")
        mi.scan(self.root, True)
        readme = self.root / "human-materials" / "README.md"
        text = readme.read_text(encoding="utf-8").replace("| Filename only; content not reviewed. | TXT (extension) | unknown | unread | — |",
                                                         "| Signed supplier contract. | TXT | legal | reviewed | 2026-10-01 |")
        readme.write_text(text, encoding="utf-8")
        mi.index(self.root, True, runner=Runner())
        self.assertEqual(self.rows()["contract.txt"]["status"], "reviewed")
        path.write_text("v2", encoding="utf-8")
        result = mi.index(self.root, True, runner=Runner())
        self.assertEqual(result["proposals"], ["contract.txt"])
        self.assertIn("Signed supplier contract.", readme.read_text(encoding="utf-8"))
        self.assertEqual(mi.status(self.root)["proposals_for_reviewed_rows"], 1)

    def test_privacy_policy_and_credential_content_never_reach_the_model(self):
        self.mode("summarize", exclude=["private/*"])
        self.put(".env.local", "TOKEN=1")
        self.put("bank-password-list.txt", "x")
        self.put("private/notes.txt", "x")
        self.put("leak.txt", "key sk-" + "a" * 30)
        runner = Runner()
        result = mi.index(self.root, True, runner=runner)
        self.assertEqual(runner.calls, [])
        self.assertEqual(len(result["skipped"]), 4)
        self.assertTrue(all(r["status"] == "unread" for r in self.rows().values()))
        self.assertEqual(mi.index(self.root, True, runner=runner)["skipped"], [])

    def test_failure_is_partial_and_budget_carries_queue(self):
        self.mode("summarize", max_files_per_run=1)
        self.put("a.txt", "first document")
        self.put("b.txt", "second document")
        result = mi.index(self.root, True, runner=Runner(fail=True))
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["remaining"], 1)
        runner = Runner()
        mi.index(self.root, True, runner=runner)
        mi.index(self.root, True, runner=runner)
        self.assertEqual({r["status"] for r in self.rows().values()}, {"ai-draft"})

    def test_office_extraction_and_unparseable_status(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>Quarterly offer</w:t></w:r></w:p></w:body></w:document>')
        docx = self.put("offer.docx", buffer.getvalue())
        self.assertEqual(mi.extract(docx, 1000)[:2], ("Quarterly offer", "full"))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", '<sst xmlns="x"><si><t>Revenue</t></si></sst>')
        self.assertEqual(mi.extract(self.put("sheet.xlsx", buffer.getvalue()), 1000)[1], "full")
        self.assertEqual(mi.extract(self.put("clip.mp4", b"\x00"), 1000)[1], "unparseable")
        self.assertEqual(mi.extract(self.put("long.txt", "x" * 50), 10)[1], "partial")
        self.mode("summarize")
        mi.index(self.root, True, runner=Runner())
        self.assertEqual(self.rows()["clip.mp4"]["status"], "unparseable")
        self.assertEqual(hm.check(self.root), [])

    def test_recall_offers_matching_summary(self):
        self.mode("summarize")
        self.put("plan.md", "Spring launch plan.")
        mi.index(self.root, True, runner=Runner())
        entries = mr.materials(self.root, mr.terms("what is the launch budget"))
        self.assertEqual(len(entries), 1)
        self.assertIn("human-materials/plan.md", entries[0])
        self.assertEqual(mr.materials(self.root, mr.terms("unrelated database migration")), [])
        boilerplate = ("Use only supplied project memory. Do not use tools or read files. "
                       "Summarize quasar neutrino magnetosphere research notes, or answer NONE.")
        self.assertEqual(mr.materials(self.root, mr.terms(boilerplate)), [])
        self.assertEqual(len(mr.materials(self.root, mr.terms("Use project memory: what is the spring launch budget?"))), 1)
        self.assertIn("1 indexed file", mr.materials(self.root, set())[0])

    def test_invalid_index_fails_closed_without_deleting_rows(self):
        self.put("a.txt", "x")
        mi.scan(self.root, True)
        readme = self.root / "human-materials" / "README.md"
        broken = readme.read_text(encoding="utf-8").replace("| unread | — |", "| unread | — |\n| [ghost](ghost.txt) | bad |")
        readme.write_text(broken, encoding="utf-8")
        with self.assertRaises(ValueError):
            mi.scan(self.root, True)
        self.assertEqual(readme.read_text(encoding="utf-8"), broken)

    def test_index_edit_during_scan_aborts(self):
        self.put("a.txt", "x")
        readme = self.root / "human-materials" / "README.md"
        real = mi.inventory
        def edited(root, cfg, state):
            out = real(root, cfg, state)
            readme.write_text(readme.read_text(encoding="utf-8") + "\nowner edit\n", encoding="utf-8")
            return out
        mi.inventory = edited
        try:
            with self.assertRaises(ValueError):
                mi.scan(self.root, True)
        finally:
            mi.inventory = real
        self.assertTrue(readme.read_text(encoding="utf-8").endswith("owner edit\n"))
        self.assertFalse(any(p.name.endswith(".tmp") for p in (self.root / "human-materials").iterdir()))

    def test_mode_off_during_run_stops_reading(self):
        self.mode("summarize")
        self.put("a.txt", "first document")
        self.put("b.txt", "second document")
        test = self
        class OptOut(Runner):
            def __call__(self, prompt, image, timeout):
                test.mode("off")
                return super().__call__(prompt, image, timeout)
        runner = OptOut()
        result = mi.index(self.root, True, runner=runner)
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("stopped", result)

    def test_rows_are_inserted_outside_long_fences(self):
        readme = self.root / "human-materials" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n\x60\x60\x60\x60text\n\x60\x60\x60\n| Material | x | x | x | x | x |\n\x60\x60\x60\x60\n", encoding="utf-8")
        self.put("a.txt", "x")
        mi.scan(self.root, True)
        self.assertEqual(hm.check(self.root), [])

    def test_policy_files_are_not_opened_for_hashing(self):
        self.put("db-password.txt", "x")
        opened = []
        real = mi.file_sha
        mi.file_sha = lambda path: opened.append(path.name) or real(path)
        try:
            mi.scan(self.root, True)
        finally:
            mi.file_sha = real
        self.assertEqual(opened, [])

    def test_exclusions_apply_mid_run_and_in_recall(self):
        self.mode("summarize")
        self.put("a.txt", "launch plan one")
        self.put("b.txt", "launch plan two")
        test = self
        class Exclude(Runner):
            def __call__(self, prompt, image, timeout):
                test.mode("summarize", exclude=["b.txt", "a.txt"])
                return super().__call__(prompt, image, timeout)
        runner = Exclude()
        mi.index(self.root, True, runner=runner)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(mr.materials(self.root, mr.terms("launch plan")), [])

    def test_metadata_only_identity_never_moves_a_row(self):
        old = self.put("old-password.txt", "x")
        mi.scan(self.root, True)
        stamp = old.stat().st_mtime_ns
        old.unlink()
        other = self.put("new-password.txt", "y")
        import os
        os.utime(other, ns=(stamp, stamp))
        self.assertEqual(mi.scan(self.root, True)["moved"], {})

    def test_fence_closer_with_text_does_not_close(self):
        readme = self.root / "human-materials" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n\x60\x60\x60\n\x60\x60\x60 not a closer\n| [x](x.txt) | a | b | c | unread | — |\n\x60\x60\x60\n", encoding="utf-8")
        self.assertEqual(hm.check(self.root), [])

    def test_opt_out_during_extraction_sends_nothing(self):
        self.mode("summarize")
        self.put("a.txt", "launch plan")
        real = mi.extract
        def extract(path, limit):
            self.mode("off")
            return real(path, limit)
        mi.extract = extract
        runner = Runner()
        try:
            mi.index(self.root, True, runner=runner)
        finally:
            mi.extract = real
        self.assertEqual(runner.calls, [])
        self.assertEqual(self.rows()["a.txt"]["status"], "unread")

    def test_opt_out_during_model_call_publishes_nothing(self):
        self.mode("summarize")
        self.put("a.txt", "launch plan")
        test = self
        class Off(Runner):
            def __call__(self, prompt, image, timeout):
                test.mode("off")
                return super().__call__(prompt, image, timeout)
        mi.index(self.root, True, runner=Off())
        self.assertEqual(self.rows()["a.txt"]["status"], "unread")

    def test_private_no_ai_row_tag_is_respected(self):
        self.put("notes.txt", "launch plan")
        mi.scan(self.root, True)
        readme = self.root / "human-materials" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("| unknown | unread |", "| private-no-ai | unread |"), encoding="utf-8")
        self.mode("summarize")
        runner = Runner()
        mi.index(self.root, True, runner=runner)
        self.assertEqual(runner.calls, [])
        self.assertIn("private-no-ai", self.rows()["notes.txt"]["text"])

    def test_old_lock_of_live_process_is_not_taken(self):
        import os
        lock = self.root / mi.LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        os.utime(lock, (1, 1))
        self.assertIsNone(mi.acquire(self.root))
        lock.write_text(json.dumps({"pid": 2 ** 30}), encoding="utf-8")
        os.utime(lock, (1, 1))
        self.assertIsNotNone(mi.acquire(self.root))

    def test_file_changed_during_summary_is_not_published(self):
        self.mode("summarize")
        path = self.put("a.txt", "launch plan")
        class Edit(Runner):
            def __call__(self, prompt, image, timeout):
                path.write_text("rewritten", encoding="utf-8")
                return super().__call__(prompt, image, timeout)
        result = mi.index(self.root, True, runner=Edit())
        self.assertEqual(self.rows()["a.txt"]["status"], "unread")
        self.assertEqual(result["state"], "partial")

    def test_private_no_ai_tag_hides_existing_summary_from_recall(self):
        self.mode("summarize")
        self.put("plan.md", "Spring launch plan.")
        mi.index(self.root, True, runner=Runner())
        readme = self.root / "human-materials" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8").replace("launch, budget", "launch, budget, private-no-ai"), encoding="utf-8")
        self.assertEqual(mr.materials(self.root, mr.terms("launch budget")), [])

    def test_failed_git_check_fails_closed(self):
        (self.root / ".git").mkdir()
        real = mi.subprocess.run
        mi.subprocess.run = lambda *a, **k: real(["python", "-c", "raise SystemExit(128)"], capture_output=True)
        try:
            with self.assertRaises(ValueError):
                mi.private(self.root)
        finally:
            mi.subprocess.run = real


WINDOWS_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>m</Description><URI>\\Dreamdocs-x</URI></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>S-1-5-21-1</UserId><LogonType>InteractiveToken</LogonType></Principal></Principals>
  <Settings><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT20M</ExecutionTimeLimit><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable><IdleSettings><StopOnIdleEnd>true</StopOnIdleEnd></IdleSettings></Settings>
  <Triggers><CalendarTrigger><StartBoundary>2026-10-24T03:15:00</StartBoundary><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
  <Actions Context="Author"><Exec><Command>py</Command><Arguments>a</Arguments><WorkingDirectory>w</WorkingDirectory></Exec></Actions>
</Task>"""
SENT_XML = ('<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task" version="1.2"><RegistrationInfo><Description>m</Description></RegistrationInfo>'
            '<Triggers><CalendarTrigger><StartBoundary>2026-10-25T03:15:00</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>'
            '<Principals><Principal id="Author"><UserId>host\\w</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>'
            '<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>'
            '<StartWhenAvailable>true</StartWhenAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT1200S</ExecutionTimeLimit></Settings>'
            '<Actions Context="Author"><Exec><Command>py</Command><Arguments>a</Arguments><WorkingDirectory>w</WorkingDirectory></Exec></Actions></Task>')


class ScheduleNormalizationTest(unittest.TestCase):
    def test_windows_normalized_readback_matches_sent_task(self):
        ds._SIDS["host\\w"] = "S-1-5-21-1"
        selection = {"name": "Dreamdocs-x", "signature": ds.task_signature(SENT_XML)}
        task = {"name": "Dreamdocs-x", "xml": WINDOWS_XML.split("\n", 1)[1]}
        self.assertTrue(ds.same_task(task, selection))
        ds._SIDS["host\\w"] = "S-1-5-21-2"
        self.assertFalse(ds.same_task(task, selection))
        ds._SIDS["host\\w"] = "S-1-5-21-1"
        idle = dict(task, xml=task["xml"].replace("<StartWhenAvailable>", "<RunOnlyIfIdle>true</RunOnlyIfIdle><StartWhenAvailable>"))
        self.assertFalse(ds.same_task(idle, selection))
        self.assertEqual(ds.seconds("PT20M"), "PT1200S")
        self.assertEqual(ds.seconds("P1DT1H"), "PT90000S")


if __name__ == "__main__":
    unittest.main()

