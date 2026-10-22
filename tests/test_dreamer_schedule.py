from datetime import datetime, timedelta, timezone
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_dreamer_executor as fixture
import dreamer_executor as de
import dreamer_schedule as ds
import project_memory as pm


class FakeBackend:
    def __init__(self):
        self.tasks = []
        self.calls = []
    def query(self):
        return copy.deepcopy(self.tasks)
    def create(self, name, xml):
        self.calls.append("create")
        if any(t["name"] == name for t in self.tasks):
            raise ValueError("duplicate")
        self.tasks.append({"name": name, "xml": xml, "state": 3, "last_run_at": None, "last_result": None})
    def disable(self, name):
        self.calls.append("disable")
        for task in self.tasks:
            if task["name"] == name:
                task["state"] = 1
                xml = ds.ET.fromstring(task["xml"])
                xml.find("t:Settings/t:Enabled", ds.NS).text = "false"
                task["xml"] = ds.ET.tostring(xml, encoding="unicode")
    def remove(self, name):
        self.calls.append("remove")
        self.tasks = [t for t in self.tasks if t["name"] != name]


class ScheduleTests(unittest.TestCase):
    setUp = fixture.ExecutorTests.setUp
    configure = fixture.ExecutorTests.configure
    command = fixture.ExecutorTests.command

    def enable(self):
        self.command("import sys\nsys.exit(7)\n")
        self.config["scheduler"] = {"backend": "windows-task-scheduler", "enabled": True, "windows_user": "DOMAIN\\owner"}
        self.configure()
        cfg = pm.settings(self.root)
        cfg["schedule"].update(timezone="UTC", local_time="01:00", owner="operator")
        pm.atomic(self.root / "memory/config.json", cfg)

    def test_preview_unconfigured_and_disabled_never_install_any_task(self):
        backend = FakeBackend()
        result = ds.manage(self.root, "install", backend=backend)
        self.assertNotEqual(result["exit"], 0)
        self.assertEqual(backend.calls, [])
        self.enable()
        with patch.object(ds, "local_zone_matches", return_value=True):
            result = ds.manage(self.root, "install", backend=backend)
        self.assertEqual(result["exit"], 0, result)
        self.assertFalse(result["applied"])
        self.assertIn("InteractiveToken", result["plan"]["xml"])
        self.assertIn("IgnoreNew", result["plan"]["xml"])
        self.assertIn("StartWhenAvailable", result["plan"]["xml"])
        self.assertEqual(backend.calls, [])

    def test_install_duplicate_prevention_disable_remove_and_exact_ownership(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=True):
            installed = ds.manage(self.root, "install", apply=True, backend=backend)
            self.assertEqual((installed["exit"], installed["applied"]), (0, True), installed)
            repeat = ds.manage(self.root, "install", apply=True, backend=backend)
            self.assertEqual(repeat["state"], "already_installed")
            backend.tasks.append({**backend.tasks[0], "name": "Dreamdocs-duplicate"})
            self.assertNotEqual(ds.manage(self.root, "install", apply=True, backend=backend)["exit"], 0)
            backend.tasks.pop()
            self.assertEqual(ds.manage(self.root, "disable", apply=True, backend=backend)["exit"], 0)
            self.assertEqual(ds.manage(self.root, "status", backend=backend)["state"], "disabled")
            self.assertEqual(ds.manage(self.root, "remove", apply=True, backend=backend)["exit"], 0)
        self.assertEqual(backend.calls, ["create", "disable", "remove"])

    def test_modified_task_or_running_task_is_never_overwritten_or_removed(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=True):
            ds.manage(self.root, "install", apply=True, backend=backend)
            original = backend.tasks[0]["xml"]
            backend.tasks[0]["xml"] = original.replace("IgnoreNew", "Parallel")
            self.assertNotEqual(ds.manage(self.root, "remove", apply=True, backend=backend)["exit"], 0)
            backend.tasks[0]["xml"] = original
            backend.tasks[0]["state"] = 4
            self.assertNotEqual(ds.manage(self.root, "remove", apply=True, backend=backend)["exit"], 0)
        self.assertEqual(backend.calls, ["create"])

    def test_owner_pause_or_executor_removal_still_allows_explicit_schedule_cleanup(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=True):
            ds.manage(self.root, "install", apply=True, backend=backend)
            self.config["paused"] = True
            self.config["executor"] = None
            self.configure()
            self.assertEqual(ds.manage(self.root, "disable", apply=True, backend=backend)["exit"], 0)
            self.assertEqual(ds.manage(self.root, "remove", apply=True, backend=backend)["exit"], 0)

    def test_changed_config_or_timezone_and_backend_denial_are_not_health_or_install_success(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=False):
            self.assertNotEqual(ds.manage(self.root, "install", apply=True, backend=backend)["exit"], 0)
        with patch.object(ds, "local_zone_matches", return_value=True):
            with patch.object(backend, "query", side_effect=OSError("access denied")):
                self.assertNotEqual(ds.manage(self.root, "install", apply=True, backend=backend)["exit"], 0)
            plan = ds.manage(self.root, "install", apply=True, backend=backend)["plan"]
            self.config["executor"]["timeout_seconds"] += 1; self.configure()
            self.assertNotEqual(ds.scheduled_gate(self.root, plan["schedule_id"], backend=backend)["exit"], 0)

    def test_success_requires_observed_trigger_time_executor_outcome_and_checkpoint_readback(self):
        self.enable(); backend = FakeBackend()
        self.command("import json,sys\nfrom pathlib import Path\ns=json.loads(Path(sys.argv[1]).read_text())\nPath(sys.argv[2]).write_text(json.dumps({'run_id':s['run_id'],'status':'success','summary':'Synthetic schedule transport.','reviewed_ids':[r['metadata']['id'] for r in s['records']],'proposals':[]}))\n")
        with patch.object(ds, "local_zone_matches", return_value=True):
            plan = ds.manage(self.root, "install", apply=True, backend=backend)["plan"]
            gate = ds.scheduled_gate
            with patch.object(ds, "scheduled_gate", side_effect=lambda root, ident: gate(root, ident, backend=backend)):
                result = de.run(self.root, "operator", trigger="scheduled", schedule_id=plan["schedule_id"])
            self.assertEqual(result["exit"], 0, result)
            self.assertNotEqual(ds.manage(self.root, "status", backend=backend)["exit"], 0)
            backend.tasks[0].update(last_run_at=result["execution"]["requested_at"], last_result=0)
            self.assertEqual(ds.manage(self.root, "status", backend=backend)["state"], "observed_success")
            pm.atomic(self.root / "memory/dreamer/state.json", {"version": 1, "last_successful_at": pm.now(), "last_run_id": "other", "source_hashes": {}})
            self.assertNotEqual(ds.manage(self.root, "status", backend=backend)["exit"], 0)

    def test_catchup_is_one_consolidated_run_since_last_success_and_duplicate_tick_is_quiet(self):
        self.enable(); backend = FakeBackend()
        now = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)
        with patch.object(ds, "local_zone_matches", return_value=True):
            plan = ds.manage(self.root, "install", apply=True, backend=backend)["plan"]
            due = ds.scheduled_gate(self.root, plan["schedule_id"], backend=backend, now=now)
            self.assertEqual(due["state"], "due", due)
            self.assertEqual(due["catchup_runs"], 1)
            pm.atomic(self.root / "memory/dreamer/state.json", {"version": 1, "last_successful_at": now.isoformat(), "completed_at": now.isoformat(), "last_run_id": "observed-run", "source_hashes": {}})
            done = ds.scheduled_gate(self.root, plan["schedule_id"], backend=backend, now=now)
            self.assertEqual(done["state"], "not_due")
            self.assertFalse(done["notify"])
            self.config["paused"] = True; self.configure()
            self.assertNotEqual(ds.scheduled_gate(self.root, plan["schedule_id"], backend=backend, now=now)["exit"], 0)

    def test_scheduler_configuration_is_never_reported_as_runtime_health(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=True):
            ds.manage(self.root, "install", apply=True, backend=backend)
            status = ds.manage(self.root, "status", backend=backend)
        self.assertEqual(status["state"], "installed_unobserved")
        self.assertNotEqual(status["health"], "healthy")

    def test_malformed_task_or_local_plan_xml_returns_blocked_without_scheduler_mutation(self):
        self.enable(); backend = FakeBackend()
        with patch.object(ds, "local_zone_matches", return_value=True):
            selection = ds.manage(self.root, "install", apply=True, backend=backend)["plan"]
            original = backend.tasks[0]["xml"]
            backend.tasks[0]["xml"] = "<Task"
            for action in ("status", "install", "disable", "remove"):
                result = ds.manage(self.root, action, apply=True, backend=backend)
                self.assertEqual(result["state"], "blocked")
                self.assertNotEqual(result["exit"], 0)
            backend.tasks[0]["xml"] = original
            record = pm.read_json(self.root / ds.INSTALL)
            record["plan"]["xml"] = "<Task"
            pm.atomic(self.root / ds.INSTALL, record)
            self.assertEqual(ds.scheduled_gate(self.root, selection["schedule_id"], backend=backend)["state"], "blocked")
        self.assertEqual(backend.calls, ["create"])


if __name__ == "__main__":
    unittest.main()
