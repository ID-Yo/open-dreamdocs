#!/usr/bin/env python3
"""Persist task outcome events as episodes and receipts (issue #16); standard library only, no network or model."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_contract as ac
import project_memory as pm

RECEIPTS, PENDING = "memory/automation/receipts", "memory/automation/pending"
PLAN_FIELDS = {"version", "event_id", "payload_sha256", "decision", "outcome", "episode"}
READMES = {
    "memory/automation": "# Automation\n\nState for automatic capture, defined in `docs/operations/automation-contract.md`. `receipts/` holds one small committed receipt per saved event. `events/` (exact event files written by an adapter) and `pending/` (captures queued while the writer lock or a Dreamer run was busy) are private local runtime folders: Git ignores them and validation skips them. Neither holds memory records.\n",
    "memory/automation/receipts": "# Capture receipts\n\nOne JSON receipt per saved event ID: payload hash, decision, outcome, status (`persisted` or `receipt_only`) and the episode path and hash when one was written. Receipts contain no summaries, lessons or raw event content. Refused events write no receipt.\n",
}


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure(root, folder):
    """Create an automation folder; committed folders get the README that validation requires."""
    for name in READMES:
        if folder == name or folder.startswith(name + "/"):
            path = pm.confined(root, name)
            path.mkdir(parents=True, exist_ok=True)
            if not (path / "README.md").exists():
                atomic_text(path / "README.md", READMES[name])
    path = pm.confined(root, folder)
    path.mkdir(parents=True, exist_ok=True)
    return path


def render(event, eid):
    outcome, task = event["outcome"], event["task"]
    meta = {"id": f"auto-{eid}", "type": "episodic", "status": "active", "project": event["project_id"],
            "scope": f"task:{task['id']}" if task else "session", "created_at": event["occurred_at"],
            "source": outcome["evidence"] + [f"ref:{event['adapter']}/{event['session_id']}/{event['turn_id']}"],
            "pinned": False}
    title = f"# Outcome: {outcome['status']}" + (f" ({task['id']}, reported {task['status']})" if task else "")
    lines = ["---", json.dumps(meta, ensure_ascii=False, indent=2), "---", "", title, "", outcome["summary"].strip(), ""]
    if outcome["lessons"]:
        lines += ["## Proposed lessons (not accepted)", ""] + [f"- {lesson.strip()}" for lesson in outcome["lessons"]] + [""]
    lines += [f"Captured automatically from {event['adapter']} by {event['agent']} in worktree {event['worktree']}.", ""]
    return "\n".join(lines)


def make_plan(event, result):
    episode = render(event, result["event_id"]) if result["decision"] == "capture_episode" else None
    return {"version": 1, "event_id": result["event_id"], "payload_sha256": result["payload_sha256"],
            "decision": result["decision"], "outcome": event["outcome"]["status"], "episode": episode}


def receipt_path(root, eid):
    return pm.confined(root, f"{RECEIPTS}/{eid}.json")


def write_receipt(root, plan, status, episode=None, episode_sha256=None):
    receipt = {"version": 1, "event_id": plan["event_id"], "payload_sha256": plan["payload_sha256"],
               "decision": plan["decision"], "outcome": plan["outcome"], "status": status, "episode": episode,
               "episode_sha256": episode_sha256, "recorded_at": pm.now()}
    ensure(root, RECEIPTS)
    path = receipt_path(root, plan["event_id"])
    pm.atomic(path, receipt)
    if pm.read_json(path) != receipt:
        raise OSError("receipt readback mismatch")
    return receipt


def verify_sources(root, meta, items):
    try:
        pm.validate_record(meta, "episodes")
        ids = {item["metadata"]["id"] for item in items}
        pm.require({item["metadata"]["project"] for item in items} <= {meta["project"]}, "memory belongs to another project")
        for ref in meta["source"]:
            if ref.startswith("id:"):
                pm.require(ref[3:] in ids, f"unknown source ID {ref[3:]}")
            elif ref.startswith("file:"):
                pm.require(pm.confined(root, ref[5:]).is_file(), f"missing source file {ref[5:]}")
    except (ValueError, TypeError) as exc:
        raise Invalid(str(exc)) from exc


def publish(root, plan, items):
    """Episode first (create, read back), then receipt (write, read back). Returns the decision."""
    path = receipt_path(root, plan["event_id"])
    if path.exists():
        existing = pm.read_json(path)
        ac.validate_receipt(existing)
        if existing["payload_sha256"] != plan["payload_sha256"]:
            raise Conflict("same identity, different payload")
        return "duplicate"
    if plan["episode"] is None:
        write_receipt(root, plan, "receipt_only")
        return plan["decision"]
    relative = f"memory/episodes/auto-{plan['event_id']}.md"
    episode, data = pm.confined(root, relative), plan["episode"].encode("utf-8")
    verify_sources(root, pm.metadata(plan["episode"]), items)
    if episode.exists():
        if episode.read_bytes() != data:
            raise Conflict("existing episode differs from this event")
    else:
        atomic_text(episode, plan["episode"])
    if episode.read_bytes() != data:
        raise OSError("episode readback mismatch")
    write_receipt(root, plan, "persisted", relative, pm.digest(data))
    return plan["decision"]


def pending_files(root):
    folder = pm.confined(root, PENDING)
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def queue(root, plan):
    path = ensure(root, PENDING) / f"{plan['event_id']}.json"
    if not path.exists():
        pm.atomic(path, plan)


def session(root, own):
    """Run under the writer lock with no Dreamer run active: drain the queue, then publish own plan."""
    items, results = pm.records(root), {}
    plans = []
    for path in pending_files(root):
        plan = pm.read_json(path)
        pm.require(set(plan) == PLAN_FIELDS and plan.get("version") == 1, f"invalid pending capture {path.name}")
        plans.append((plan, path))
    if own is not None and own["event_id"] not in {plan["event_id"] for plan, _ in plans}:
        plans.append((own, None))
    for plan, path in plans:
        try:
            results[plan["event_id"]] = (publish(root, plan, items), [])
        except Conflict as exc:
            results[plan["event_id"]] = ("conflict", [str(exc)])
            continue
        except Invalid as exc:
            results[plan["event_id"]] = ("invalid", [str(exc)])
        if path is not None:
            path.unlink()
    return results


@contextlib.contextmanager
def writer(root):
    """Yield True when the shared writer lock is held and no Dreamer run is active; never take over a lock."""
    try:
        lock = pm.operation(root)
        lock.__enter__()
    except pm.MemoryError:
        yield False
        return
    try:
        yield not pm.runtime(root, "lock.json").exists()
    finally:
        lock.__exit__(None, None, None)


def outcome_exit(decision, outcome):
    if decision == "capture_episode" and outcome in {"partial", "failed"}:
        return 1
    return {"capture_episode": 0, "receipt_only": 0, "duplicate": 0, "invalid": 2, "conflict": 5}[decision]


def capture(root, event, budget=1.0):
    root = Path(root).resolve()
    binding_path = pm.confined(root, "memory/automation.json")
    try:
        binding = pm.read_json(binding_path) if binding_path.is_file() else None
    except (OSError, ValueError) as exc:
        return {"decision": "invalid", "exit": 2, "saved": False, "event_id": None, "findings": [f"unreadable binding: {exc}"]}
    result = ac.check(event, binding)
    report = {"event_id": result["event_id"], "receipt": result["receipt"], "saved": False, "findings": result["findings"]}
    try:
        if result["decision"] not in {"capture_episode", "receipt_only"}:
            return {**report, "decision": result["decision"], "exit": result["exit"]}
        own = make_plan(event, result)
        deadline, queued = time.monotonic() + budget, False
        while True:
            with writer(root) as free:
                if free:
                    decision, findings = session(root, own)[own["event_id"]]
                    return {**report, "decision": decision, "exit": outcome_exit(decision, own["outcome"]),
                            "saved": decision not in {"invalid", "conflict"}, "findings": findings}
            dreamer = pm.runtime(root, "lock.json").exists()
            if not queued:
                queue(root, own)
                queued = True
            if dreamer or time.monotonic() >= deadline:
                return {**report, "decision": "queued", "exit": 1,
                        "findings": ["writer lock busy or Dreamer run active; capture queued as pending, not saved yet"]}
            time.sleep(0.05)
    except (OSError, ValueError) as exc:
        return {**report, "decision": "error", "exit": 2, "findings": [f"not saved: {exc}"]}


def reconcile(root):
    root = Path(root).resolve()
    with writer(root) as free:
        if not free:
            return {"decision": "queued", "exit": 1, "published": 0, "pending": len(pending_files(root)),
                    "findings": ["writer lock busy or Dreamer run active"]}
        results = session(root, None)
    published = sum(decision not in {"invalid", "conflict"} for decision, _ in results.values())
    conflicts = sorted(eid for eid, (decision, _) in results.items() if decision == "conflict")
    return {"decision": "reconciled", "exit": 5 if conflicts else 0, "published": published,
            "pending": len(pending_files(root)), "conflicts": conflicts}

