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
        self.assertIn("1 indexed file", mr.materials(self.root, set())[0])


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
        self.assertEqual(ds.seconds("PT20M"), "PT1200S")
        self.assertEqual(ds.seconds("P1DT1H"), "PT90000S")


if __name__ == "__main__":
    unittest.main()

