#!/usr/bin/env python3
"""Check one automation lifecycle event against the v1 contract; read-only, never captures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime

sys.dont_write_bytecode = True
KINDS = {"session_start", "task_start", "task_outcome", "session_end"}
PRIVACY = {"public", "project", "restricted", "prohibited"}
OUTCOMES = {"success", "no_lesson", "partial", "failed", "interrupted"}
TASK_STATUSES = {"backlog", "ready", "in-progress", "review", "blocked", "paused", "done"}
IDENTITY = ("adapter", "session_id", "turn_id", "kind", "project_id", "worktree", "agent")
FIELDS = {"version", "privacy", "occurred_at", "task", "outcome", *IDENTITY}
RECEIPT_FIELDS = {"version", "event_id", "payload_sha256", "decision", "outcome", "status", "episode", "episode_sha256", "recorded_at"}
RECEIPT_STATUSES = {"persisted", "receipt_only"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MISSING = object()  # no receipt file; any existing file content, including null, is validated
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
TEXT_LIMIT, LESSON_LIMIT, MAX_LESSONS, MAX_EVIDENCE = 2000, 600, 10, 20
EXIT = {"capture_episode": 0, "receipt_only": 0, "recall_only": 0, "duplicate": 0,
        "retry_pending": 1, "invalid": 2, "reject": 3, "degraded": 4, "conflict": 5}
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_|\bAKIA[0-9A-Z]{16}\b|BEGIN [A-Z ]*PRIVATE KEY", re.I)
# Candidate 1.5.0-rc.1: adapters/fixtures ship, but final exact-candidate dual-client gates remain.
# Earlier Codex trusted-session proof is described in docs/operations/support-matrix.md.
# Only accepted runtime evidence may change state to "tested", with client_version/os/surface/tested_at/evidence.
SUPPORT = {
    "codex": {"state": "unsupported", "observed_client": "codex-cli 0.147.0", "os": "Windows 10.0.26100"},
    "claude-code": {"state": "unsupported", "observed_client": "Claude Code 2.1.273", "os": "Windows 10.0.26100"},
}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def event_id(event):
    return "evt-" + hashlib.sha256(canonical({k: event.get(k) for k in IDENTITY}).encode()).hexdigest()[:32]


def text(value, limit=200):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate_event(event):
    require(isinstance(event, dict) and set(event) == FIELDS, "event fields must be exactly: " + ", ".join(sorted(FIELDS)))
    require(type(event["version"]) is int and event["version"] == 1, "unsupported event version")
    require(event["kind"] in KINDS and event["adapter"] in SUPPORT and event["privacy"] in PRIVACY, "unknown kind/adapter/privacy")
    require(all(text(event[k]) for k in IDENTITY), "identity fields must be nonempty text")
    require(LABEL.fullmatch(event["worktree"]), "worktree must be a short label without path separators or drive prefix")
    require(LABEL.fullmatch(event["agent"]), "agent must be a short label such as a role or bot ID")
    require(isinstance(event["occurred_at"], str) and "T" in event["occurred_at"]
            and datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00")).tzinfo is not None, "occurred_at needs a timezone")
    task = event["task"]
    require(task is None or isinstance(task, dict) and set(task) == {"id", "status"} and text(task["id"]) and task["status"] in TASK_STATUSES, "invalid task")
    outcome = event["outcome"]
    if event["kind"] != "task_outcome":
        require(outcome is None, "only task_outcome carries an outcome")
        return
    require(isinstance(outcome, dict) and set(outcome) == {"status", "summary", "evidence", "lessons"}, "invalid outcome fields")
    require(outcome["status"] in OUTCOMES and text(outcome["summary"], TEXT_LIMIT), "invalid outcome status/summary")
    evidence, lessons = outcome["evidence"], outcome["lessons"]
    require(isinstance(evidence, list) and len(evidence) <= MAX_EVIDENCE and all(
        text(r) and r.startswith(("id:", "file:", "https://", "ref:")) for r in evidence), "evidence needs id:, file:, https:// or ref:")
    require(isinstance(lessons, list) and len(lessons) <= MAX_LESSONS and all(text(v, LESSON_LIMIT) for v in lessons), "lessons must be short text")
    require(evidence or outcome["status"] in {"no_lesson", "interrupted"}, "captured outcome needs evidence")


def validate_binding(binding):
    require(isinstance(binding, dict) and type(binding.get("version")) is int, "binding needs an integer version")
    require(binding["version"] == 1, "unsupported binding version; no migration is attempted")
    require(set(binding) == {"version", "project_id", "adapters"} and text(binding["project_id"]), "invalid binding fields")
    require(isinstance(binding["adapters"], list) and set(binding["adapters"]) <= set(SUPPORT), "unknown adapter in binding")


def validate_receipt(receipt):
    require(isinstance(receipt, dict) and type(receipt.get("version")) is int, "receipt must be an object with an integer version")
    require(receipt["version"] == 1, "unsupported receipt version; no migration is attempted")
    require(set(receipt) == RECEIPT_FIELDS, "invalid receipt fields")
    require(isinstance(receipt["event_id"], str) and isinstance(receipt["payload_sha256"], str)
            and SHA256.fullmatch(receipt["payload_sha256"]) and isinstance(receipt["status"], str)
            and receipt["status"] in RECEIPT_STATUSES, "invalid receipt values")
    require(re.fullmatch(r"evt-[0-9a-f]{32}", receipt["event_id"]), "invalid receipt identity")
    require(isinstance(receipt["outcome"], str) and receipt["outcome"] in OUTCOMES - {"interrupted"}, "invalid receipt outcome")
    require(isinstance(receipt["decision"], str) and receipt["decision"] in {"capture_episode", "receipt_only"}, "invalid persisted receipt decision")
    try:
        timestamp = datetime.fromisoformat(receipt["recorded_at"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError("invalid receipt timestamp") from exc
    require(timestamp.tzinfo is not None, "receipt timestamp requires timezone")
    if receipt["status"] == "persisted":
        require(receipt["decision"] == "capture_episode" and receipt["outcome"] != "no_lesson", "persisted receipt requires captured outcome")
        require(receipt["episode"] == f"memory/episodes/auto-{receipt['event_id']}.md"
                and isinstance(receipt["episode_sha256"], str) and SHA256.fullmatch(receipt["episode_sha256"]), "persisted receipt needs exact episode identity/hash")
    else:
        require(receipt["decision"] == "receipt_only" and receipt["episode"] is None and receipt["episode_sha256"] is None,
                "receipt_only must have receipt_only decision and null episode/hash")


def decide(event, binding, receipt=MISSING):
    try:
        validate_event(event)
    except (ContractError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return "invalid", [str(exc)]
    if event["privacy"] == "prohibited" or SECRET.search(canonical(event)):
        return "reject", ["prohibited privacy class or credential-like content"]
    if binding is None:
        return "degraded", ["project has no automation binding; capture is manual, not automatic"]
    try:
        validate_binding(binding)
    except ContractError as exc:
        return "invalid", [str(exc)]
    if event["project_id"] != binding["project_id"]:
        return "reject", ["event belongs to another project"]
    if event["adapter"] not in binding["adapters"]:
        return "degraded", [f"adapter {event['adapter']} is not installed for this project"]
    if receipt is not MISSING:
        try:
            validate_receipt(receipt)
        except ContractError as exc:
            return "invalid", [str(exc)]
        same = receipt.get("event_id") == event_id(event) and receipt.get("payload_sha256") == hashlib.sha256(canonical(event).encode()).hexdigest()
        return ("duplicate", ["already persisted"]) if same else ("conflict", ["same identity, different payload"])
    if event["kind"] != "task_outcome":
        return "recall_only", []
    status = event["outcome"]["status"]
    if status == "interrupted":
        return "retry_pending", ["outcome unknown; redeliver the same identity"]
    if event["task"] and event["task"]["status"] == "paused":
        return "receipt_only", ["task is paused; recorded without resuming work"]
    if status == "no_lesson" or event["privacy"] == "restricted":
        return "receipt_only", []
    return "capture_episode", []


def check(event, binding, receipt=MISSING):
    decision, findings = decide(event, binding, receipt)
    eid = event_id(event) if isinstance(event, dict) else None
    exit_code = EXIT[decision]
    if decision == "capture_episode" and event["outcome"]["status"] in {"partial", "failed"}:
        exit_code = 1
    adapter = event.get("adapter") if isinstance(event, dict) else None
    return {"ok": exit_code == 0, "decision": decision, "exit": exit_code, "findings": findings, "event_id": eid,
            "payload_sha256": hashlib.sha256(canonical(event).encode()).hexdigest(),
            "receipt": f"memory/automation/receipts/{eid}.json" if eid else None,
            "episode": f"memory/episodes/auto-{eid}.md" if eid else None,
            "support": SUPPORT.get(adapter, {}).get("state"), "automatic": SUPPORT.get(adapter, {}).get("state") == "tested",
            "resume_authorized": False, "promotion": "review-required"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        event = read(Path(args.event))
        binding_path = root / "memory" / "automation.json"
        binding = read(binding_path) if binding_path.is_file() else None
        receipt = MISSING
        if isinstance(event, dict) and binding is not None:
            receipt_path = root / "memory" / "automation" / "receipts" / f"{event_id(event)}.json"
            receipt = read(receipt_path) if receipt_path.is_file() else MISSING
        result = check(event, binding, receipt)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))  # ASCII-escaped: safe in any console code page
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())

