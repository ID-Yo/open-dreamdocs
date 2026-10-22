#!/usr/bin/env python3
"""Shared lifecycle hook logic for the Codex and Claude Code adapters (issues #18, #19).

Never blocks or continues the agent, never reads transcripts and never calls a model.
SessionStart recalls the project briefing; meaningful prompts recall related memory; Stop saves the
turn outcome from an optional fenced dreamdocs-outcome block in the last assistant message;
StopFailure (Claude Code) is an interrupted turn and writes nothing; SessionEnd only publishes queued
captures. All output is ASCII JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_contract as ac
import memory_capture as mc
import memory_recall as mr
import project_memory as pm

BLOCK = re.compile(r"```dreamdocs-outcome[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
BLOCK_FIELDS = {"status", "summary", "lessons", "evidence", "task"}
MEANINGFUL_TERMS = 3
SESSION_CHARS, PROMPT_CHARS, PROMPT_QUERY = 4000, 2000, 500
CAPTURE_BUDGET = 5.0
REDELIVER_MAX, REDELIVER_BUDGET = 5, 2.0


def emit(value):
    sys.stdout.write(json.dumps(value) + "\n")


def binding(root):
    path = root / "memory" / "automation.json"
    return pm.read_json(path) if path.is_file() else None


def context(event, result, notes=()):
    output = {}
    if result["status"] == "ok" and result["context"]:
        output["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": result["context"]}
    if notes:
        output["systemMessage"] = "Dreamdocs memory: " + "; ".join(notes)
    if output:
        emit(output)


def redeliver(root, skip=None):
    """Publish event files left by an earlier failed or killed Stop; bounded in count and time."""
    folder = root / "memory" / "automation" / "events"
    if not folder.is_dir():
        return []
    notes, deadline = [], time.monotonic() + REDELIVER_BUDGET
    leftovers = [p for p in sorted(folder.glob("*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name)) if p.stem != skip]
    for path in leftovers[:REDELIVER_MAX]:
        if time.monotonic() >= deadline:
            break
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            notes.append(f"unreadable event file {path.name} left in place")
            continue
        result = mc.capture(root, event, 0.2)
        if result["saved"]:
            path.unlink(missing_ok=True)
        elif result["decision"] not in {"queued", "error"}:  # those retry on a later hook
            notes.append(f"earlier turn {path.stem} {result['decision']}; event file left in place")
    return notes


def session_start(root):
    notes = redeliver(root)
    context("SessionStart", mr.recall(root, max_chars=SESSION_CHARS), notes)


def user_prompt(root, payload):
    prompt = payload.get("prompt") if isinstance(payload.get("prompt"), str) else ""
    if len(mr.terms(prompt)) >= MEANINGFUL_TERMS:
        context("UserPromptSubmit", mr.recall(root, query=prompt[:PROMPT_QUERY], max_chars=PROMPT_CHARS, episodes=3))


def outcome_block(message, adapter, turn):
    """Return (outcome, task, warning). Only an explicit block can carry lessons; nothing is invented."""
    found = BLOCK.findall(message)
    if found:
        try:
            data = json.loads(found[-1])
            if isinstance(data, dict) and set(data) <= BLOCK_FIELDS and isinstance(data.get("summary"), str):
                evidence = data.get("evidence") or [f"ref:{adapter}-turn/{turn}"]
                return ({"status": data.get("status", "success"), "summary": data["summary"],
                         "lessons": data.get("lessons", []), "evidence": evidence}, data.get("task"), None)
        except ValueError:
            pass
        warning = "outcome block is not valid; saved as a receipt without lessons"
    else:
        warning = None
    summary = f"{adapter} turn finished without a dreamdocs-outcome block."
    return {"status": "no_lesson", "summary": summary, "lessons": [], "evidence": []}, None, warning


def stop(root, adapter, turn_of, payload):
    if payload.get("stop_hook_active"):
        return {}
    bound = binding(root)
    if bound is None:
        return {"systemMessage": "Dreamdocs memory is not installed in this project; nothing was saved."}
    message = payload.get("last_assistant_message") if isinstance(payload.get("last_assistant_message"), str) else ""
    session, turn = str(payload.get("session_id") or "unknown"), turn_of(payload)
    outcome, task, warning = outcome_block(message, adapter, turn)
    event = {"version": 1, "kind": "task_outcome", "adapter": adapter, "session_id": session, "turn_id": turn,
             "project_id": bound.get("project_id"), "worktree": re.sub(r"[^A-Za-z0-9._-]", "-", root.name)[:64].lstrip("-._") or "project",
             "agent": adapter, "occurred_at": pm.now(), "privacy": "project", "task": task, "outcome": outcome}
    eid = ac.event_id(event)
    notes = redeliver(root, skip=eid)
    if mc.receipt_path(root, eid).is_file():
        return {"systemMessage": "Dreamdocs memory: " + "; ".join(notes)} if notes else {}  # already saved; never rebuild a turn
    stored = pm.confined(root, f"memory/automation/events/{eid}.json")
    if stored.is_file():
        event = json.loads(stored.read_text(encoding="utf-8"))  # redeliver the exact bytes saved before the first delivery
    else:
        checked = ac.check(event, bound)
        if checked["decision"] in {"reject", "invalid", "degraded"}:
            notes.append(f"capture {checked['decision']}; nothing was saved")
            return {"systemMessage": "Dreamdocs memory: " + "; ".join(notes)}
        stored.parent.mkdir(parents=True, exist_ok=True)
        mc.atomic_text(stored, json.dumps(event, ensure_ascii=False, sort_keys=True))
    result = mc.capture(root, event, CAPTURE_BUDGET)
    if result["saved"]:
        stored.unlink(missing_ok=True)
    notes += [warning] if warning else []
    if not result["saved"]:
        notes.append(f"capture {result['decision']} (exit {result['exit']})")
    return {"systemMessage": "Dreamdocs memory: " + "; ".join(notes)} if notes else {}


def session_end(root):
    if mc.pending_files(root):
        mc.reconcile(root)


def main(root, adapter, turn_of):
    """Run one hook invocation. Always exits 0; Stop always prints one JSON object."""
    event = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
        event = payload.get("hook_event_name") if isinstance(payload, dict) else None
        if event == "Stop":
            emit(stop(root, adapter, turn_of, payload))
        elif event == "SessionStart":
            session_start(root)
        elif event == "UserPromptSubmit":
            user_prompt(root, payload)
        elif event == "SessionEnd":
            session_end(root)
        # StopFailure is an interrupted turn under the contract: nothing is written and nothing is printed.
    except Exception as exc:  # a memory hook must never break or block the agent
        if event == "Stop":
            emit({"systemMessage": f"Dreamdocs memory hook error: {type(exc).__name__}; nothing was saved."})
    return 0
