"""Separately opted-in Windows Task Scheduler backend; configured/installed/observed are distinct."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import dreamer_executor as de
import project_memory as pm

INSTALL = ".dreamdocs/dreamer-schedule.json"
NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
NS = {"t": NAMESPACE}


class WindowsBackend:
    """Fixed COM operations; values arrive as JSON data, never interpolated PowerShell source."""
    def call(self, action, name=None, xml=None):
        pm.require(os.name == "nt", "Windows Task Scheduler is unavailable on this host")
        script = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$req = [Console]::In.ReadToEnd() | ConvertFrom-Json
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$folder = $service.GetFolder('\')
switch ($req.action) {
  'query' {
    $tasks = @($folder.GetTasks(1) | Where-Object { $_.Name.StartsWith('Dreamdocs-') -or $_.Xml.Contains('--schedule-id') } | ForEach-Object {
      $last = $null
      if ($_.LastRunTime.Year -gt 2000) { $last = $_.LastRunTime.ToUniversalTime().ToString('o') }
      @{ name=$_.Name; xml=$_.Xml; state=[int]$_.State; last_run_at=$last; last_result=$_.LastTaskResult }
    })
    ConvertTo-Json -InputObject $tasks -Depth 4 -Compress
  }
  'create' { $null = $folder.RegisterTask($req.name, $req.xml, 2, $null, $null, 3, $null); '{}' }
  'validate' { $null = $folder.RegisterTask($req.name, $req.xml, 1, $null, $null, 3, $null); '{}' }
  'disable' { $folder.GetTask($req.name).Enabled = $false; '{}' }
  'remove' { $folder.DeleteTask($req.name, 0); '{}' }
  default { throw 'Unsupported scheduler action' }
}
'''
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                input=json.dumps({"action": action, "name": name, "xml": xml}).encode("ascii"),
                                capture_output=True, timeout=20,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pm.require(result.returncode == 0, "Windows scheduler operation unavailable/denied; no health or install success assumed")
        return json.loads(result.stdout.decode("utf-8-sig"))

    def query(self):
        result = self.call("query")
        pm.require(isinstance(result, list) and all(isinstance(t, dict) for t in result), "invalid scheduler inventory")
        return result
    def create(self, name, xml):
        self.call("create", name, xml)
    def validate(self, name, xml):
        self.call("validate", name, xml)  # TASK_VALIDATE_ONLY; creates no task
    def disable(self, name):
        self.call("disable", name)
    def remove(self, name):
        self.call("remove", name)


def local_zone_matches(zone):
    # Floating Windows daily triggers follow the host zone. Reject other zones, including DST drift.
    now = datetime.now(timezone.utc)
    return all((now + timedelta(days=n)).astimezone().utcoffset() == (now + timedelta(days=n)).astimezone(zone).utcoffset()
               for n in (0, 90, 180, 270))


def plan(root):
    root, cfg, config_sha = de.configuration(root)
    scheduler = cfg["scheduler"]
    pm.require(scheduler and scheduler["enabled"] and not cfg["paused"], "scheduler is not explicitly enabled or project is paused")
    pm.require(cfg["executor"]["kind"] == "command", "operator-only executor cannot be installed unattended")
    schedule = pm.settings(root)["schedule"]
    pm.require(all(schedule[k] for k in ("timezone", "local_time", "owner")), "complete explicit schedule owner/timezone/local_time required")
    pm.require(schedule["owner"] == cfg["executor"]["id"], "schedule owner must match selected executor")
    zone = ZoneInfo(schedule["timezone"])
    pm.require(local_zone_matches(zone), "project schedule timezone must match host timezone/DST; no silent timezone conversion")
    schedule_id = pm.digest((cfg["project_id"] + "\n" + str(root)).encode())[:24]
    name = "Dreamdocs-" + pm.digest(cfg["project_id"].encode())[:24]
    marker = "dreamdocs-project:" + pm.digest(cfg["project_id"].encode())
    script = pm.confined(root, "scripts/dreamdocs.py")
    argv = ["-B", str(script), "--root", str(root), "dreamer", "run", "--executor", cfg["executor"]["id"], "--trigger", "scheduled", "--schedule-id", schedule_id]
    now = datetime.now(zone)
    boundary = now.replace(hour=int(schedule["local_time"][:2]), minute=int(schedule["local_time"][3:]), second=0, microsecond=0)
    ET.register_namespace("", NAMESPACE)
    task = ET.Element("{" + NAMESPACE + "}Task", {"version": "1.2"})
    def node(parent, name, value=None):
        child = ET.SubElement(parent, "{" + NAMESPACE + "}" + name)
        if value is not None:
            child.text = value
        return child
    info = node(task, "RegistrationInfo"); node(info, "Description", marker)
    triggers = node(task, "Triggers"); daily = node(triggers, "CalendarTrigger")
    node(daily, "StartBoundary", boundary.replace(tzinfo=None).isoformat())
    node(daily, "Enabled", "true"); node(node(daily, "ScheduleByDay"), "DaysInterval", "1")
    principal = node(node(task, "Principals"), "Principal"); principal.set("id", "Author")
    node(principal, "UserId", scheduler["windows_user"]); node(principal, "LogonType", "InteractiveToken"); node(principal, "RunLevel", "LeastPrivilege")
    settings = node(task, "Settings")
    for key, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("DisallowStartIfOnBatteries", "false"), ("StopIfGoingOnBatteries", "false"),
                       ("StartWhenAvailable", "true"), ("AllowStartOnDemand", "true"), ("Enabled", "true"), ("WakeToRun", "false"),
                       ("ExecutionTimeLimit", "PT" + str(cfg["executor"]["timeout_seconds"] + 300) + "S")):
        node(settings, key, value)
    actions = node(task, "Actions"); actions.set("Context", "Author"); command = node(actions, "Exec")
    node(command, "Command", str(Path(sys.executable).absolute()))
    node(command, "Arguments", subprocess.list2cmdline(argv)); node(command, "WorkingDirectory", str(root))
    xml = ET.tostring(task, encoding="unicode")
    return {"name": name, "schedule_id": schedule_id, "project_marker": marker, "project_id": cfg["project_id"], "root": str(root),
            "executable": str(Path(sys.executable).absolute()), "argv": argv, "owner": scheduler["windows_user"],
            "timezone": schedule["timezone"], "local_time": schedule["local_time"], "config_sha256": config_sha,
            "xml": xml, "signature": task_signature(xml), "catchup": "at most one consolidated run from last successful checkpoint", "interactive_logon_required": True}


def task_signature(xml):
    # COM may normalize XML formatting and identity attributes; compare every operational field used here.
    pm.require(isinstance(xml, str) and len(xml) <= 131072, "invalid scheduler XML")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError("malformed scheduler task XML; observation blocked without task mutation") from error
    fields = ("RegistrationInfo/Description", "Triggers/CalendarTrigger/StartBoundary", "Triggers/CalendarTrigger/Enabled",
              "Triggers/CalendarTrigger/ScheduleByDay/DaysInterval", "Principals/Principal/UserId", "Principals/Principal/LogonType",
              "Principals/Principal/RunLevel", "Actions/Exec/Command", "Actions/Exec/Arguments", "Actions/Exec/WorkingDirectory")
    signature = {p: root.findtext("/".join("t:" + part for part in p.split("/")), namespaces=NS) for p in fields}
    settings = root.find("t:Settings", NS)
    managed = {"MultipleInstancesPolicy", "DisallowStartIfOnBatteries", "StopIfGoingOnBatteries", "StartWhenAvailable", "AllowStartOnDemand", "Enabled", "WakeToRun", "ExecutionTimeLimit"}
    signature["settings"] = {child.tag.rsplit("}", 1)[-1]: child.text for child in settings if child.tag.rsplit("}", 1)[-1] in managed} if settings is not None else {}
    pm.require(root.find("t:Settings/t:RestartOnFailure", NS) is None, "automatic task retries are not configured")
    pm.require(len(root.findall("t:Actions/t:Exec", NS)) == 1 and len(root.findall("t:Triggers/*", NS)) == 1
               and len(root.findall("t:Actions/*", NS)) == 1 and len(root.findall("t:Principals/*", NS)) == 1, "unexpected additional task actions/triggers/principals")
    return signature


def relevant(tasks, selection):
    return [t for t in tasks if t.get("name") == selection["name"] or selection["project_marker"] in t.get("xml", "")
            or ("dreamdocs.py" in t.get("xml", "") and selection["root"] in t.get("xml", ""))]


def same_task(task, selection, enabled=True):
    actual, expected = task_signature(task["xml"]), selection["signature"]
    # Installation date is preserved across later status/disable calls; daily clock must still match.
    boundary = actual.get("Triggers/CalendarTrigger/StartBoundary")
    wanted = expected["Triggers/CalendarTrigger/StartBoundary"]
    if not boundary or boundary[11:] != wanted[11:]:
        return False
    actual["Triggers/CalendarTrigger/StartBoundary"] = wanted
    if not enabled:
        actual["settings"]["Enabled"] = "true"
    return task["name"] == selection["name"] and actual == expected


@de.guarded
def manage(root, action="status", apply=False, backend=None):
    root = Path(root).resolve(); backend = backend or WindowsBackend()
    record_path = pm.confined(root, INSTALL)
    installed = pm.read_json(record_path, {})
    selection = plan(root) if action == "install" or not installed else installed["plan"]
    bound = pm.read_json(pm.confined(root, "memory/automation.json"))
    pm.require(selection["root"] == str(root) and selection["project_id"] == bound["project_id"]
               and selection["name"] == "Dreamdocs-" + pm.digest(bound["project_id"].encode())[:24], "local scheduler installation identity mismatch")
    tasks = relevant(backend.query(), selection)
    pm.require(len(tasks) <= 1, "duplicate project schedules detected; resolve explicitly before any operation")
    report = {"exit": 0, "state": "planned", "applied": False, "plan": selection, "health": "unknown", "notify": False}
    pm.require(action in {"install", "status", "disable", "remove"}, "unknown scheduler operation")
    if not tasks:
        if action != "install":
            report.update(exit=1, state="not_installed")
            return report
    else:
        task = tasks[0]
        pm.require(same_task(task, selection, enabled=task["state"] != 1), "installed task differs from selected owner/action/schedule; never overwrite it")
        pm.require(installed.get("schedule_id") == selection["schedule_id"] and installed.get("config_sha256") == selection["config_sha256"], "existing task lacks matching local installation identity")
        if action == "install":
            report["state"] = "already_installed" if task["state"] != 1 else "disabled"
            return report
        if action == "status":
            report.update(exit=1, state="disabled" if task["state"] == 1 else "running" if task["state"] in {2, 4} else "installed_unobserved", observation=task)
            runtime = de.status(root)
            execution = runtime.get("last_execution")
            if task["state"] == 3 and runtime.get("exit") == 0 and execution and execution.get("state") == "success" and execution.get("trigger") == "scheduled" and task.get("last_result") == 0 and task.get("last_run_at"):
                delta = abs((pm.timestamp(task["last_run_at"]) - pm.timestamp(execution["requested_at"])).total_seconds())
                if delta <= 300:
                    report.update(exit=0, state="observed_success", health="observed_success", executor=execution["executor_id"], run_id=execution["run_id"])
            return report
        pm.require(task["state"] not in {2, 4}, "task is running or queued; do not disable/remove uncertain live work")
    if not apply:
        return report
    with pm.operation(root):
        pm.require(not pm.runtime(root, "lock.json").exists(), "Dreamer active; scheduler mutation deferred")
        pm.require(relevant(backend.query(), selection) == tasks, "scheduler changed during preflight")
        if action == "install":
            pm.require(plan(root)["config_sha256"] == selection["config_sha256"], "config changed during preflight")
            de.private_runtime(root, [INSTALL])
        if action == "install":
            backend.create(selection["name"], selection["xml"])
            current = relevant(backend.query(), selection)
            pm.require(len(current) == 1 and same_task(current[0], selection), "scheduler install readback mismatch; inspect task before retry")
            pm.atomic(record_path, {"version": 1, "schedule_id": selection["schedule_id"], "config_sha256": selection["config_sha256"], "installed_at": pm.now(),
                                   "name": selection["name"], "root": str(root), "project_id": selection["project_id"], "signature": selection["signature"], "plan": selection})
            report.update(state="installed_unobserved", health="unknown")
        elif action == "disable":
            backend.disable(selection["name"])
            current = relevant(backend.query(), selection)
            pm.require(len(current) == 1 and current[0]["state"] == 1 and same_task(current[0], selection, False), "disable readback mismatch")
            report["state"] = "disabled"
        else:
            backend.remove(selection["name"])
            pm.require(not relevant(backend.query(), selection), "remove readback mismatch")
            record_path.unlink(missing_ok=True)
            report["state"] = "removed"
        report["applied"] = True
    return report


@de.guarded
def scheduled_gate(root, schedule_id, backend=None, now=None):
    root = Path(root).resolve()
    selection = plan(root)
    pm.require(schedule_id == selection["schedule_id"], "scheduled invocation does not match installed project/root identity")
    installed = pm.read_json(pm.confined(root, INSTALL))
    pm.require(installed.get("config_sha256") == selection["config_sha256"]
               and same_task({"name": installed.get("name"), "xml": installed.get("plan", {}).get("xml")}, selection),
               "schedule/executor settings changed since install; review and reinstall before automatic execution")
    observed = manage(root, "status", backend=backend)
    pm.require(observed.get("state") in {"installed_unobserved", "observed_success", "running"}, "schedule disabled, missing or unverified; invocation deferred")
    pm.require(not pm.runtime(root, "lock.json").exists() and not pm.runtime(root, "command.lock").exists(), "writer/run already active; no duplicate catch-up")
    cfg = pm.settings(root)["schedule"]
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(cfg["timezone"]))
    boundary = local.replace(hour=int(cfg["local_time"][:2]), minute=int(cfg["local_time"][3:]), second=0, microsecond=0)
    if boundary > local:
        boundary -= timedelta(days=1)
    checkpoint = pm.read_json(pm.runtime(root, "state.json"), {})
    if checkpoint.get("last_successful_at") and pm.timestamp(checkpoint["last_successful_at"]) >= boundary:
        return {"exit": 0, "state": "not_due", "notify": False, "catchup_runs": 0}
    return {"exit": 0, "state": "due", "catchup_runs": 1, "from_checkpoint": checkpoint.get("last_successful_at"), "due_at": boundary.isoformat(), "notify": False}
