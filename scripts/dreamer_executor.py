"""Explicit operator/command Dreamer execution; no scheduler or model is enabled by default."""
from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import automation_contract as ac
import project_memory as pm

CONFIG = ".dreamdocs/dreamer.json"
RUNS = ".dreamdocs/dreamer-runs"
LATEST = ".dreamdocs/dreamer-latest.json"
BUDGETS = {"timeout_seconds", "max_records", "max_input_bytes", "max_result_bytes", "max_proposals"}


class Unconfigured(ValueError):
    pass


class ProcessTreeUncertain(ValueError):
    pass


def guarded(call):
    @wraps(call)
    def run(*args, **kwargs):
        try:
            return call(*args, **kwargs)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as error:
            return {"exit": 4, "state": "unconfigured" if isinstance(error, Unconfigured) else "blocked", "checkpoint_advanced": False,
                    "cause": type(error).__name__, "detail": str(error),
                    "next_action": "Inspect explicit executor configuration/evidence and owning run. Do not take over live locks or retry uncertain external operations."}
    return run


def configuration(root):
    root = Path(root).resolve()
    path = pm.confined(root, CONFIG)
    if not path.is_file():
        raise Unconfigured("No explicit Dreamer executor configured")
    pm.require(path.stat().st_size <= pm.SOURCE_HASH_LIMIT, "executor config exceeds size limit")
    cfg_bytes = path.read_bytes()
    cfg = json.loads(cfg_bytes, object_pairs_hook=pm.unique_keys)
    pm.require(isinstance(cfg, dict), "executor config must be an object")
    pm.require(set(cfg) == {"version", "project_id", "paused", "evidence_files", "executor", "scheduler"} and type(cfg["version"]) is int and cfg["version"] == 1, "invalid executor config version/fields")
    bound = pm.read_json(pm.confined(root, "memory/automation.json"))
    ac.validate_binding(bound)
    pm.require(cfg["project_id"] == bound["project_id"] and type(cfg["paused"]) is bool, "project/pause mismatch")
    pm.require(isinstance(cfg["evidence_files"], list) and all(isinstance(p, str) for p in cfg["evidence_files"]), "evidence_files must be selected relative paths")
    if cfg["executor"] is None:
        raise Unconfigured("Executor is explicitly unconfigured; no execution started")
    worker = cfg["executor"]
    pm.require(isinstance(worker, dict) and set(worker) == {"id", "kind", "argv", *BUDGETS}, "invalid executor fields")
    pm.require(isinstance(worker["id"], str) and pm.IDENTIFIER.fullmatch(worker["id"]) and worker["kind"] in {"operator", "command"}, "invalid executor identity/kind")
    pm.require(all(type(worker[k]) is int and 0 < worker[k] for k in BUDGETS) and worker["timeout_seconds"] <= 86400, "positive bounded executor budgets required")
    if worker["kind"] == "operator":
        pm.require(worker["argv"] is None, "operator executor has no command")
    else:
        pm.require(isinstance(worker["argv"], list) and worker["argv"] and all(isinstance(a, str) and "\x00" not in a for a in worker["argv"])
                   and Path(worker["argv"][0]).is_absolute(), "command requires explicit absolute executable and argv; no shell")
    pm.require(cfg["scheduler"] is None or isinstance(cfg["scheduler"], dict) and set(cfg["scheduler"]) == {"backend", "enabled", "windows_user"}
               and cfg["scheduler"]["backend"] == "windows-task-scheduler" and type(cfg["scheduler"]["enabled"]) is bool
               and ac.text(cfg["scheduler"]["windows_user"]), "invalid optional scheduler configuration")
    pm.require(not ac.SECRET.search(ac.canonical(cfg)), "credential-like executor configuration refused")
    return root, cfg, pm.digest(cfg_bytes)


def available(root, executor):
    root, cfg, sha = configuration(root)
    pm.require(not cfg["paused"], "Dreamer is owner-paused")
    pm.require(executor == cfg["executor"]["id"], "select the configured executor identity explicitly")
    return root, cfg, sha


def context_path(root, run):
    pm.require(isinstance(run, str) and pm.IDENTIFIER.fullmatch(run), "invalid run identity")
    return pm.confined(root, RUNS + "/" + run + ".json")


def store(root, execution):
    private_runtime(root, [RUNS + "/" + execution["run_id"] + ".json", LATEST])
    path = context_path(root, execution["run_id"])
    pm.atomic(path, execution)
    pm.require(pm.read_json(path) == execution, "execution receipt readback mismatch")
    pm.atomic(pm.confined(root, LATEST), {"version": 1, "run_id": execution["run_id"], "sha256": pm.digest(path.read_bytes())})


def private_runtime(root, destinations):
    ignore = pm.confined(root, ".dreamdocs/.gitignore")
    if not ignore.exists():
        from memory_capture import atomic_text
        atomic_text(ignore, "*\n")
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=5)
    repo = git("rev-parse", "--is-inside-work-tree")
    if repo.returncode:
        pm.require(not any((p / ".git").exists() for p in (root, *root.parents)), "Git worktree privacy could not be verified")
        return  # local non-Git execution; no Git exclusion guarantee after later adoption
    paths = [CONFIG, *destinations]
    tracked = git("ls-files", "-z", "--", *paths)
    pm.require(tracked.returncode == 0 and not tracked.stdout, "private executor configuration/receipts are tracked; untrack explicitly before running")
    for relative in paths:
        pm.confined(root, relative)
        pm.require(not any((p / ".git").exists() for p in (root / relative).parents if p != root and p.is_relative_to(root)), "private runtime crosses a nested repository")
        pm.require(git("check-ignore", "-q", "--", relative).returncode == 0, "private executor configuration/receipt is not effectively Git-ignored; preserve/review owner ignore rules")


def evidence(root, cfg, snapshot):
    selected = set(cfg["evidence_files"]) | {"AGENTS.md", "docs/governance/promotion-rules.md"}
    for record in snapshot["records"]:
        selected |= {s[5:] for s in record["metadata"]["source"] if s.startswith("file:")}
    hashes, size = {}, 0
    for relative in sorted(selected):
        pm.require(not relative.replace("\\", "/").casefold().startswith("human-materials/")
                   and not any(p.casefold().startswith(".env") for p in Path(relative).parts), "original/credential evidence needs a separate consented reader; not read by this executor wrapper")
        path = pm.confined(root, relative)
        pm.require(path.is_file() and path.stat().st_size <= pm.SOURCE_HASH_LIMIT, "missing or oversized selected evidence")
        raw = path.read_bytes()
        hashes[relative] = pm.digest(raw)
        size += len(raw)
    return hashes, size


@guarded
def begin(root, executor, trigger="manual"):
    root, cfg, sha = available(root, executor)
    pm.require(trigger in {"manual", "scheduled"}, "invalid trigger")
    if trigger == "scheduled":
        pm.require(cfg["executor"]["kind"] == "command", "operator-only executor cannot run unattended")
    requested = pm.now()
    result = pm.begin(root)
    run = result["run_id"]
    try:
        with pm.operation(root):
            snapshot, work = pm.run_files(root, run)
            hashes, size = evidence(root, cfg, snapshot)
            hashes[CONFIG] = sha
            hashes["memory/automation.json"] = pm.digest(pm.confined(root, "memory/automation.json").read_bytes())
            worker = cfg["executor"]
            pm.require(len(snapshot["records"]) <= worker["max_records"] and (work / "snapshot.json").stat().st_size + size <= worker["max_input_bytes"], "selected input exceeds executor budget; nothing was executed")
            pm.require(configuration(root)[2] == sha, "executor config changed during preparation")
            execution = {"version": 1, "project_id": cfg["project_id"], "root": str(root), "run_id": run,
                         "executor_id": executor, "executor_kind": worker["kind"], "config_sha256": sha,
                         "argv_sha256": pm.digest(ac.canonical(worker["argv"]).encode()), "budgets": {k: worker[k] for k in sorted(BUDGETS)},
                         "trigger": trigger, "requested_at": requested, "prepared_at": pm.now(), "started_at": None, "finished_at": None,
                         "state": "prepared", "pid": None, "process_exit": None, "process_finished_at": None, "result_sha256": None, "report_sha256": None,
                         "snapshot_sha256": pm.digest((work / "snapshot.json").read_bytes()), "evidence_hashes": hashes,
                         "checkpoint": None, "proposal_hashes": {}, "provenance": "Operator timestamps are explicit operator reports; command timestamps/PID/exit are locally observed. No semantic truth attestation."}
            store(root, execution)
        return {"exit": 0, "state": "prepared", "run_id": run, "execution": execution, "snapshot": result["snapshot"]}
    except (OSError, ValueError):
        # This run has not dispatched an executor, so aborting our own preparation cannot steal live work.
        pm.abort(root, run)
        raise


def load_execution(root, run, executor):
    root, cfg, sha = available(root, executor)
    execution = pm.read_json(context_path(root, run))
    pm.require(execution["version"] == 1 and execution["run_id"] == run and execution["project_id"] == cfg["project_id"]
               and execution["executor_id"] == executor and execution["root"] == str(root) and execution["config_sha256"] == sha, "execution identity/config revision mismatch")
    snapshot, work = pm.run_files(root, run)
    pm.require(execution["snapshot_sha256"] == pm.digest((work / "snapshot.json").read_bytes()), "execution snapshot mismatch")
    pm.require(all(pm.digest(pm.confined(root, p).read_bytes()) == h for p, h in execution["evidence_hashes"].items()), "selected review evidence changed")
    return root, cfg, execution, snapshot, work


@guarded
def start(root, run, executor):
    root = Path(root).resolve()
    with pm.operation(root):
        root, cfg, execution, _, _ = load_execution(root, run, executor)
        pm.require(cfg["executor"]["kind"] == "operator" and execution["state"] == "prepared", "only a prepared operator run can be explicitly started")
        execution.update(state="running", started_at=pm.now())
        store(root, execution)
    return {"exit": 0, "state": "running", "run_id": run, "execution": execution}


@guarded
def finish(root, run, executor):
    root, cfg, execution, snapshot, work = load_execution(root, run, executor)
    pm.require(execution["state"] == "running" and execution["started_at"], "executor has not actually started")
    pm.require(cfg["executor"]["kind"] == "operator" or execution["process_exit"] == 0, "command executor has not finished successfully")
    pm.require((datetime.now(timezone.utc) - pm.timestamp(execution["started_at"])).total_seconds() <= cfg["executor"]["timeout_seconds"], "executor deadline exceeded; confirm stopped work before explicit abort/recovery")
    path = work / "result.json"
    pm.require(path.stat().st_size <= cfg["executor"]["max_result_bytes"], "result byte budget exceeded")
    result_bytes = path.read_bytes()
    result = json.loads(result_bytes, object_pairs_hook=pm.unique_keys)
    pm.validate_result(snapshot, result)
    pm.require(len(result["proposals"]) <= cfg["executor"]["max_proposals"] and not ac.SECRET.search(ac.canonical(result)), "proposal budget or credential policy refused result")
    result_sha = pm.digest(result_bytes)
    outcome = pm.finish(root, run, expected_result_sha256=result_sha, evidence_hashes=execution["evidence_hashes"])
    with pm.operation(root):
        report_path = pm.runtime(root, "reports/" + run + ".json")
        report = pm.read_json(report_path)
        state = pm.read_json(pm.runtime(root, "state.json"), {})
        pm.require(report["run_id"] == run and report["status"] == result["status"], "executor report readback mismatch")
        if result["status"] == "success":
            pm.require(state.get("last_run_id") == run and state.get("source_hashes") == snapshot["manifest"], "success report has no matching committed checkpoint")
        proposals = {"memory/dreamer/proposals/" + p + ".json": pm.digest(pm.runtime(root, "proposals/" + p + ".json").read_bytes()) for p in report["proposal_ids"]}
        execution.update(state=result["status"], finished_at=pm.now(), result_sha256=result_sha,
                         report_sha256=pm.digest(report_path.read_bytes()), checkpoint=state or None, proposal_hashes=proposals)
        store(root, execution)
    return {"exit": 0 if result["status"] == "success" else 1, "state": result["status"], "run_id": run,
            "checkpoint_advanced": outcome["checkpoint_advanced"], "execution": execution}


class OwnedProcess:
    """Keep descendants in an owned Windows Job (or POSIX process group) and join before releasing a run."""
    def __init__(self, argv, root):
        self.job = None
        self.process = None
        def launch():
            return subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                                    start_new_session=os.name != "nt")
        if os.name == "nt":
            import ctypes as ct
            from ctypes import wintypes as wt
            class Limits(ct.Structure):
                _fields_ = [("process_time", ct.c_longlong), ("job_time", ct.c_longlong), ("flags", wt.DWORD),
                            ("min_working", ct.c_size_t), ("max_working", ct.c_size_t), ("process_limit", wt.DWORD),
                            ("affinity", ct.c_size_t), ("priority", wt.DWORD), ("scheduling", wt.DWORD)]
            class Extended(ct.Structure):
                _fields_ = [("basic", Limits), ("io", ct.c_ulonglong * 6), ("process_memory", ct.c_size_t),
                            ("job_memory", ct.c_size_t), ("peak_process", ct.c_size_t), ("peak_job", ct.c_size_t)]
            self.kernel = ct.WinDLL("kernel32", use_last_error=True)
            for name, args, returns in (("CreateJobObjectW", [ct.c_void_p, wt.LPCWSTR], wt.HANDLE),
                                        ("SetInformationJobObject", [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD], wt.BOOL),
                                        ("AssignProcessToJobObject", [wt.HANDLE, wt.HANDLE], wt.BOOL),
                                        ("OpenProcess", [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
                                        ("CloseHandle", [wt.HANDLE], wt.BOOL)):
                function = getattr(self.kernel, name); function.argtypes = args; function.restype = returns
            self.job = self.kernel.CreateJobObjectW(None, None)
            limits = Extended(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            handle = None
            try:
                if not self.job or not self.kernel.SetInformationJobObject(self.job, 9, ct.byref(limits), ct.sizeof(limits)):
                    raise ct.WinError(ct.get_last_error())
                self.process = launch()
                handle = self.kernel.OpenProcess(0x0101, False, self.process.pid)  # SET_QUOTA | TERMINATE
                if not handle or not self.kernel.AssignProcessToJobObject(self.job, handle):
                    raise ct.WinError(ct.get_last_error())
            except OSError:
                self.close()
                if self.process is not None:
                    raise ProcessTreeUncertain(f"Windows Job assignment failed for owned PID {self.process.pid}; run lock retained for process-tree inspection")
                raise
            finally:
                if handle:
                    self.kernel.CloseHandle(handle)
        else:
            self.process = launch()

    def close(self):
        if os.name == "nt" and self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        elif os.name != "nt" and self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)


@guarded
def run(root, executor, trigger="manual", schedule_id=None):
    root, cfg, _ = available(root, executor)
    pm.require(cfg["executor"]["kind"] == "command", "operator executor requires explicit begin/start/result/finish; no unattended execution")
    if trigger == "scheduled":
        import dreamer_schedule
        decision = dreamer_schedule.scheduled_gate(root, schedule_id)
        if decision["state"] != "due":
            return decision
    prepared = begin(root, executor, trigger)
    if prepared["exit"]:
        return prepared
    execution, run_id = prepared["execution"], prepared["run_id"]
    with pm.operation(root):
        root, cfg, execution, _, work = load_execution(root, run_id, executor)
        pm.require(cfg["executor"]["kind"] == "command" and execution["state"] == "prepared", "command dispatch identity changed")
    replacements = {"{project}": str(root), "{run_id}": run_id, "{snapshot}": str(work / "snapshot.json"), "{result}": str(work / "result.json")}
    argv = [a for a in cfg["executor"]["argv"]]
    for key, value in replacements.items():
        argv = [a.replace(key, value) for a in argv]
    owned, failure = None, None
    try:
        owned = OwnedProcess(argv, root)
        execution.update(started_at=pm.now(), state="running", pid=owned.process.pid)
        with pm.operation(root):
            store(root, execution)
        execution["process_exit"] = owned.process.wait(timeout=cfg["executor"]["timeout_seconds"])
        execution["process_finished_at"] = pm.now()
        if execution["process_exit"] != 0:
            failure = "failed"
    except subprocess.TimeoutExpired:
        failure = "timed_out"
    except OSError:
        failure = "blocked"
    finally:
        if owned is not None:
            owned.close()  # only our Job/process group; descendants cannot keep this run alive silently
            execution["process_finished_at"] = execution["process_finished_at"] or pm.now()
    if failure:
        execution.update(state=failure, finished_at=pm.now(), process_exit=owned.process.returncode if owned is not None else None)
        pm.abort(root, run_id)  # our executor is joined (or never started); never clears another owner's run
        with pm.operation(root):
            store(root, execution)
        return {"exit": 4 if failure == "blocked" else 1, "state": failure, "run_id": run_id, "execution": execution, "checkpoint_advanced": False}
    with pm.operation(root):
        store(root, execution)
    return finish(root, run_id, executor)


@guarded
def status(root):
    root, cfg, sha = configuration(root)
    latest = pm.read_json(pm.confined(root, LATEST), {})
    last = None
    if latest:
        path = context_path(root, latest["run_id"])
        pm.require(pm.digest(path.read_bytes()) == latest["sha256"], "execution receipt modified")
        last = pm.read_json(path)
        if last["state"] == "success":
            state = pm.read_json(pm.runtime(root, "state.json"), {})
            report = pm.runtime(root, "reports/" + last["run_id"] + ".json")
            result = pm.runtime(root, "work/" + last["run_id"] + "/result.json")
            valid = (last["config_sha256"] == sha and last["project_id"] == cfg["project_id"] and last["root"] == str(root)
                     and state == last["checkpoint"] and state.get("last_run_id") == last["run_id"]
                     and pm.digest(report.read_bytes()) == last["report_sha256"] and pm.digest(result.read_bytes()) == last["result_sha256"]
                     and all(pm.digest(pm.confined(root, p).read_bytes()) == h for p, h in last["evidence_hashes"].items())
                     and all(pm.digest(pm.confined(root, p).read_bytes()) == h for p, h in last["proposal_hashes"].items())
                     and (datetime.now(timezone.utc) - pm.timestamp(last["finished_at"])).total_seconds() <= 86400)
            if not valid:
                last = {**last, "state": "unverified"}
    return {"exit": 0 if last and last["state"] == "success" and not cfg["paused"] else 1,
            "state": "paused" if cfg["paused"] else "observed" if last else "unobserved", "executor": cfg["executor"]["id"],
            "last_execution": last, "scheduler": "not_installed_or_unverified", "active_run": pm.runtime(root, "lock.json").exists(),
            "limits": "Local execution/readback proof only. Proposals remain unaccepted; a configured scheduler is not health proof."}
