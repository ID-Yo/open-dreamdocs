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


def baseline(root, refs):
    """Hash local file: evidence at capture time so recall can tell a real edit from a new checkout."""
    hashes = {}
    for ref in refs:
        if ref.startswith("file:"):
            try:
                path = pm.confined(root, ref[5:])
            except (ValueError, OSError):
                continue  # check_files refuses it
            if path.is_file():
                sha = pm.bounded_digest(path)
                if sha is not None:
                    hashes[ref] = sha
    return hashes


def render(root, event, eid):
    outcome, task = event["outcome"], event["task"]
    meta = {"id": f"auto-{eid}", "type": "episodic", "status": "active", "project": event["project_id"],
            "scope": f"task:{task['id']}" if task else "session", "created_at": event["occurred_at"],
            "source": outcome["evidence"] + [f"ref:{event['adapter']}/{event['session_id']}/{event['turn_id']}"],
            "pinned": False}
    hashes = baseline(root, outcome["evidence"])
    if hashes:
        meta["source_sha256"] = hashes
    title = f"# Outcome: {outcome['status']}" + (f" ({task['id']}, reported {task['status']})" if task else "")
    lines = ["---", json.dumps(meta, ensure_ascii=False, indent=2), "---", "", title, "", outcome["summary"].strip(), ""]
    if outcome["lessons"]:
        lines += ["## Proposed lessons (not accepted)", ""] + [f"- {lesson.strip()}" for lesson in outcome["lessons"]] + [""]
    lines += [f"Captured automatically from {event['adapter']} by {event['agent']} in worktree {event['worktree']}.", ""]
    return "\n".join(lines)


def make_plan(root, event, result):
    episode = render(root, event, result["event_id"]) if result["decision"] == "capture_episode" else None
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


def check_files(root, meta):
    """Checks that need no lock or record scan; run before queueing so the caller learns about them at once."""
    try:
        pm.validate_record(meta, "episodes")
        for ref in meta["source"]:
            if ref.startswith("file:"):
                pm.require(pm.confined(root, ref[5:]).is_file(), f"missing source file {ref[5:]}")
    except (ValueError, TypeError) as exc:
        raise Invalid(str(exc)) from exc


def verify_sources(root, meta, items):
    check_files(root, meta)
    try:
        ids = {item["metadata"]["id"] for item in items}
        pm.require({item["metadata"]["project"] for item in items} <= {meta["project"]}, "memory belongs to another project")
        for ref in meta["source"]:
            if ref.startswith("id:"):
                pm.require(ref[3:] in ids, f"unknown source ID {ref[3:]}")
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
    """Create the pending file complete or not at all; a second writer for the same ID compares payloads."""
    folder = ensure(root, PENDING)
    path = folder / f"{plan['event_id']}.json"
    temporary = folder / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        atomic_text(temporary, pm.canonical(plan))
        for _ in range(3):
            try:
                os.link(temporary, path)  # fails if another writer queued this ID first
                return
            except FileExistsError:
                try:
                    existing = pm.read_json(path)
                except FileNotFoundError:
                    continue  # drained meanwhile; try again
                if existing.get("payload_sha256") != plan["payload_sha256"]:
                    raise Conflict("a different payload with this identity is already pending")
                return
        raise OSError("pending capture kept changing; not queued")
    finally:
        temporary.unlink(missing_ok=True)


def session(root, own):
    """Run under the writer lock with no Dreamer run active: drain the queue, then publish own plan.

    Returns every result by event ID and the drained entries that stay queued (refused or conflicting)."""
    items, results, unpublished = pm.records(root), {}, []
    plans = []
    for path in pending_files(root):
        try:
            plan = pm.read_json(path)
            pm.require(set(plan) == PLAN_FIELDS and plan.get("version") == 1, "invalid fields")
        except (ValueError, OSError):
            unpublished.append({"event_id": None, "pending": path.name, "decision": "invalid",
                                "findings": [f"unreadable pending capture {path.name}; left in place"]})
            continue
        plans.append((plan, path))
    own_result = None
    if own is not None:
        queued = [plan for plan, _ in plans if plan["event_id"] == own["event_id"]]
        if queued and queued[0]["payload_sha256"] != own["payload_sha256"]:
            own_result = ("conflict", ["a different payload with this identity is already pending"])
        elif not queued:
            plans.append((own, None))
    for plan, path in plans:
        try:
            decision, findings = publish(root, plan, items), []
        except Conflict as exc:
            decision, findings = "conflict", [str(exc)]
        except Invalid as exc:
            decision, findings = "invalid", [str(exc)]
        results[plan["event_id"]] = (decision, findings)
        if decision in {"conflict", "invalid"}:
            if path is not None:
                unpublished.append({"event_id": plan["event_id"], "pending": path.name, "decision": decision, "findings": findings})
            continue
        if plan["episode"] is not None:
            items.append({"metadata": pm.metadata(plan["episode"])})
        if path is not None:
            path.unlink()
    if own_result is not None:
        results[own["event_id"]] = own_result
    return results, unpublished


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
        own = make_plan(root, event, result)
        saved = receipt_path(root, own["event_id"])
        if saved.exists():  # receipts are created atomically and never rewritten, so no lock is needed
            existing = pm.read_json(saved)
            ac.validate_receipt(existing)
            if existing["payload_sha256"] == own["payload_sha256"]:
                return {**report, "decision": "duplicate", "exit": 0, "saved": True, "findings": []}
            return {**report, "decision": "conflict", "exit": 5, "findings": ["same identity, different payload"]}
        if own["episode"] is not None:
            try:
                check_files(root, pm.metadata(own["episode"]))
            except Invalid as exc:
                return {**report, "decision": "invalid", "exit": 2, "findings": [str(exc)]}
        deadline, queued = time.monotonic() + budget, False
        while True:
            with writer(root) as free:
                if free:
                    results, unpublished = session(root, own)
                    decision, findings = results[own["event_id"]]
                    if decision == "duplicate":  # no receipt at the first check: another writer published these bytes while we waited
                        decision, findings = own["decision"], ["published by another writer while this capture waited"]
                    return {**report, "decision": decision, "exit": outcome_exit(decision, own["outcome"]),
                            "saved": decision not in {"invalid", "conflict"}, "findings": findings,
                            "unpublished": [u for u in unpublished if u["event_id"] != own["event_id"]]}
            dreamer = pm.runtime(root, "lock.json").exists()
            if not queued:
                try:
                    queue(root, own)
                except Conflict as exc:
                    return {**report, "decision": "conflict", "exit": 5, "findings": [str(exc)]}
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
        results, unpublished = session(root, None)
    published = sum(decision not in {"invalid", "conflict"} for decision, _ in results.values())
    decisions = {u["decision"] for u in unpublished}
    return {"decision": "reconciled", "exit": 5 if "conflict" in decisions else 2 if decisions else 0,
            "published": published, "pending": len(pending_files(root)), "unpublished": unpublished}

