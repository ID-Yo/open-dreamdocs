#!/usr/bin/env python3
"""Codex lifecycle hook for Dreamdocs project memory (issue #18).

Never blocks or continues the agent, never reads transcripts and never calls a model.
SessionStart and meaningful UserPromptSubmit prompts get bounded recalled context; Stop saves the turn
outcome (an optional fenced dreamdocs-outcome block in the last assistant message); SessionEnd only
publishes queued captures.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import automation_contract as ac
import memory_capture as mc
import memory_recall as mr
import project_memory as pm

BLOCK = re.compile(r"```dreamdocs-outcome[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S)
BLOCK_FIELDS = {"status", "summary", "lessons", "evidence", "task"}
NO_BLOCK = "Codex turn finished without a dreamdocs-outcome block."
MEANINGFUL_TERMS = 3
SESSION_CHARS, PROMPT_CHARS, PROMPT_QUERY = 4000, 2000, 500
CAPTURE_BUDGET = 5.0


def emit(value):
    sys.stdout.write(json.dumps(value) + "\n")


def binding():
    path = ROOT / "memory" / "automation.json"
    return pm.read_json(path) if path.is_file() else None


def context(event, result):
    if result["status"] == "ok" and result["context"]:
        emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": result["context"]}})


def session_start(payload):
    context("SessionStart", mr.recall(ROOT, max_chars=SESSION_CHARS))


def user_prompt(payload):
    prompt = payload.get("prompt") if isinstance(payload.get("prompt"), str) else ""
    if len(mr.terms(prompt)) >= MEANINGFUL_TERMS:
        context("UserPromptSubmit", mr.recall(ROOT, query=prompt[:PROMPT_QUERY], max_chars=PROMPT_CHARS, episodes=3))


def outcome_block(message, turn):
    """Return (outcome, task, warning). Only an explicit block can carry lessons; nothing is invented."""
    found = BLOCK.findall(message)
    if found:
        try:
            data = json.loads(found[-1])
            if isinstance(data, dict) and set(data) <= BLOCK_FIELDS and isinstance(data.get("summary"), str):
                evidence = data.get("evidence") or [f"ref:codex-turn/{turn}"]
                return ({"status": data.get("status", "success"), "summary": data["summary"],
                         "lessons": data.get("lessons", []), "evidence": evidence}, data.get("task"), None)
        except ValueError:
            pass
        warning = "outcome block is not valid; saved as a receipt without lessons"
    else:
        warning = None
    return {"status": "no_lesson", "summary": NO_BLOCK, "lessons": [], "evidence": []}, None, warning


def stop(payload):
    if payload.get("stop_hook_active"):
        return {}
    bound = binding()
    if bound is None:
        return {"systemMessage": "Dreamdocs memory is not installed in this project; nothing was saved."}
    message = payload.get("last_assistant_message") if isinstance(payload.get("last_assistant_message"), str) else ""
    session, turn = str(payload.get("session_id") or "unknown"), str(payload.get("turn_id") or "unknown")
    outcome, task, warning = outcome_block(message, turn)
    event = {"version": 1, "kind": "task_outcome", "adapter": "codex", "session_id": session, "turn_id": turn,
             "project_id": bound.get("project_id"), "worktree": re.sub(r"[^A-Za-z0-9._-]", "-", ROOT.name)[:64].lstrip("-._") or "project",
             "agent": "codex", "occurred_at": pm.now(), "privacy": "project", "task": task, "outcome": outcome}
    eid = ac.event_id(event)
    if mc.receipt_path(ROOT, eid).is_file():
        return {}  # this session turn is already saved; a repeated Stop must not rebuild it
    stored = pm.confined(ROOT, f"memory/automation/events/{eid}.json")
    if stored.is_file():
        event = json.loads(stored.read_text(encoding="utf-8"))  # redeliver the exact bytes saved before the first delivery
    else:
        checked = ac.check(event, bound)
        if checked["decision"] in {"reject", "invalid", "degraded"}:
            return {"systemMessage": f"Dreamdocs memory: capture {checked['decision']}; nothing was saved."}
        stored.parent.mkdir(parents=True, exist_ok=True)
        mc.atomic_text(stored, json.dumps(event, ensure_ascii=False, sort_keys=True))
    result = mc.capture(ROOT, event, CAPTURE_BUDGET)
    if result["saved"]:
        stored.unlink(missing_ok=True)
    notes = [warning] if warning else []
    if not result["saved"]:
        notes.append(f"capture {result['decision']} (exit {result['exit']})")
    return {"systemMessage": "Dreamdocs memory: " + "; ".join(notes)} if notes else {}


def session_end(payload):
    if mc.pending_files(ROOT):
        mc.reconcile(ROOT)


def main():
    event = None
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
        event = payload.get("hook_event_name") if isinstance(payload, dict) else None
        if event == "Stop":
            emit(stop(payload))
        elif event == "SessionStart":
            session_start(payload)
        elif event == "UserPromptSubmit":
            user_prompt(payload)
        elif event == "SessionEnd":
            session_end(payload)
    except Exception as exc:  # a memory hook must never break or block the agent
        if event == "Stop":
            emit({"systemMessage": f"Dreamdocs memory hook error: {type(exc).__name__}; nothing was saved."})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

