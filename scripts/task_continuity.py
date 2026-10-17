"""Audit an explicit task evidence snapshot; never dispatch, repair or schedule work."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def check(snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    findings = []

    def finding(code, scope, detail):
        findings.append({"code": code, "scope": scope, "detail": detail})

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def evidence(value):
        return isinstance(value, list) and bool(value) and all(text(v) for v in value)

    def timestamp(value, scope, field, future=False):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result.tzinfo is None or (not future and result > now):
                raise ValueError()
            return result
        except (ValueError, TypeError, AttributeError):
            finding("invalid_time", scope, field + " needs a timezone-aware observation (not future)")
            return None

    def deadline(value, scope, code):
        result = timestamp(value, scope, "next_check_at", future=True)
        if result and result <= now:
            finding(code, scope, "Next check is due; reconcile actual evidence")

    if not isinstance(snapshot, dict) or type(snapshot.get("version")) is not int or snapshot["version"] != 1:
        return {"ok": False, "findings": [{"code": "invalid_snapshot", "scope": "snapshot",
                                           "detail": "Expected version 1 object"}]}
    timestamp(snapshot.get("reconciled_at"), "snapshot", "reconciled_at")
    deadline(snapshot.get("next_check_at"), "snapshot", "reconciliation_overdue")
    tasks = snapshot.get("tasks")
    if not isinstance(tasks, list):
        finding("invalid_tasks", "snapshot", "tasks must be an explicitly reconciled array")
        tasks = []
    active = False
    seen = set()
    for task in tasks:
        if not isinstance(task, dict):
            finding("invalid_task", "unknown", "Expected task object")
            continue
        ident = task.get("id")
        scope = ident if text(ident) else "unknown"
        required = {"id", "manager", "executor", "status", "start_approved", "next_action",
                    "acceptance", "evidence", "updated_at", "next_check_at", "handoffs",
                    "blocker", "candidate", "review", "accepted"}
        if not required <= task.keys():
            finding("missing_field", scope, "Required task fields missing: " + ", ".join(sorted(required - task.keys())))
        if task.get("executor") is not None and not text(task["executor"]):
            finding("invalid_executor", scope, "executor must be identity or null")
        for key in ("blocker", "candidate", "review", "accepted"):
            if task.get(key) is not None and not isinstance(task[key], dict):
                finding("invalid_field", scope, key + " must be object or null")
        if not text(ident) or scope in seen:
            finding("invalid_id", scope, "Task IDs must be nonempty and unique")
        seen.add(scope)
        for key in ("manager", "next_action"):
            if not text(task.get(key)):
                finding("missing_field", scope, key + " is required")
        for key in ("acceptance", "evidence"):
            if not evidence(task.get(key)):
                finding("missing_field", scope, key + " needs nonempty references/criteria")
        state = task.get("status")
        if not isinstance(state, str):
            state = "invalid"
        if state not in {"backlog", "ready", "in-progress", "review", "blocked", "paused", "future", "done"}:
            finding("invalid_status", scope, "Unknown task status")
        if type(task.get("start_approved")) is not bool:
            finding("invalid_approval", scope, "start_approved must be explicit boolean")
        updated = timestamp(task.get("updated_at"), scope, "updated_at")
        excluded = state in {"backlog", "paused", "future", "done"}
        if not excluded:
            deadline(task.get("next_check_at"), scope, "task_overdue")
        started_work = not excluded and (task.get("start_approved") is True or state in {"in-progress", "review", "blocked"})
        active = active or started_work
        blocker = task.get("blocker")
        if state == "blocked":
            if not isinstance(blocker, dict) or not all(text(blocker.get(k)) for k in ("reason", "owner", "resume_condition")) or not evidence(blocker.get("evidence")):
                finding("blocker_missing", scope, "Blocked work needs reason, unblock owner, resume condition and evidence")
            else:
                deadline(blocker.get("next_check_at"), scope, "blocker_overdue")
        elif blocker is not None and state not in {"paused", "backlog", "future"}:
            finding("blocker_status", scope, "Record a current blocker using blocked status")
        handoffs = task.get("handoffs")
        if not isinstance(handoffs, list):
            finding("invalid_handoffs", scope, "handoffs must be an ordered durable array")
            handoffs = []
        ids = set()
        running = []
        for h in handoffs:
            if not isinstance(h, dict):
                finding("invalid_handoff", scope, "Expected handoff object")
                continue
            hid = h.get("id")
            if not {"id", "worker", "stage", "requested_at", "acknowledged_at", "started_at", "finished_at", "evidence"} <= h.keys():
                finding("invalid_handoff", scope, "All handoff fields are required; unobserved timestamps use null")
            if not text(hid) or hid in ids or not text(h.get("worker")) or h.get("stage") not in ("implementation", "review", "qa", "integration"):
                finding("invalid_handoff", scope, "Unique handoff ID, worker and concrete stage required")
            if text(hid):
                ids.add(hid)
            previous = None
            for field in ("requested_at", "acknowledged_at", "started_at", "finished_at"):
                value = h.get(field)
                if value is not None:
                    current = timestamp(value, scope, field)
                    if field != "requested_at" and previous is None:
                        finding("handoff_order", scope, "Request, acknowledgment, start and finish must be ordered")
                    if current and previous and current < previous:
                        finding("handoff_order", scope, "Handoff timestamps out of order")
                    previous = current
                else:
                    previous = None
            if h.get("requested_at") is None:
                finding("invalid_handoff", scope, "Durable request timestamp required")
            if not evidence(h.get("evidence")):
                finding("handoff_evidence", scope, "References to request/ack/actual activity required")
            if h.get("started_at") and not h.get("finished_at"):
                running.append(h)
        if started_work and state != "blocked":
            last = handoffs[-1] if handoffs and isinstance(handoffs[-1], dict) else {}
            if last.get("finished_at"):
                finding("stage_finished", scope, "Inspect finished turn and verify successor start or record blocker")
            elif not last.get("started_at"):
                finding("worker_not_started", scope, "Dispatch/ack/ready is not actual worker start")
            if not text(task.get("executor")) or last.get("worker") != task.get("executor"):
                finding("executor_mismatch", scope, "Current executor must match latest handoff worker")
            if len(running) != 1:
                finding("active_handoffs", scope, "Use one current stage; reconcile superseded/conflicting handoffs")
        if state == "done":
            candidate, review, accepted = (task.get(k) for k in ("candidate", "review", "accepted"))
            reviewed_at = None
            if not isinstance(candidate, dict) or not all(text(candidate.get(k)) for k in ("id", "author")):
                finding("candidate_missing", scope, "Exact immutable candidate and author identity required")
                candidate = {}
            if not isinstance(review, dict) or not text(review.get("reviewer")) or not evidence(review.get("evidence")):
                finding("review_missing", scope, "Independent review identity and evidence required")
            else:
                reviewed_at = timestamp(review.get("reviewed_at"), scope, "reviewed_at")
                if review.get("candidate") != candidate.get("id") or review.get("verdict") != "approve":
                    finding("review_mismatch", scope, "Review must approve exact accepted candidate")
                if review.get("reviewer") == candidate.get("author"):
                    finding("review_not_independent", scope, "Author PASS is not independent review")
            if not isinstance(accepted, dict) or accepted.get("by") != task.get("manager") or not evidence(accepted.get("evidence")):
                finding("acceptance_missing", scope, "Manager acceptance evidence required")
            else:
                accepted_at = timestamp(accepted.get("accepted_at"), scope, "accepted_at")
                if accepted_at and reviewed_at and accepted_at < reviewed_at:
                    finding("acceptance_order", scope, "Manager acceptance cannot precede independent review")
                if accepted.get("candidate") != candidate.get("id"):
                    finding("acceptance_mismatch", scope, "Manager must accept exact reviewed candidate")
        if updated and snapshot.get("reconciled_at"):
            reconciled = timestamp(snapshot["reconciled_at"], "snapshot", "reconciled_at")
            if reconciled and updated > reconciled:
                finding("unreconciled_task", scope, "Task update newer than snapshot reconciliation")
    runtime = snapshot.get("runtime")
    if not isinstance(runtime, dict):
        finding("runtime_missing", "runtime", "Explicit external scheduler/host observations required, including unknown")
    else:
        if (not {"scheduler", "host", "observed_at", "next_check_at", "evidence"} <= runtime.keys()
                or runtime.get("scheduler") not in ("healthy", "unhealthy", "unknown", "not_configured")
                or runtime.get("host") not in ("online", "offline", "unknown")
                or not isinstance(runtime.get("evidence"), list)
                or not all(text(v) for v in runtime.get("evidence", []))):
            finding("invalid_runtime", "runtime", "Explicit valid scheduler/host observation fields required")
        if active:
            if runtime.get("scheduler") != "healthy" or runtime.get("host") != "online" or not evidence(runtime.get("evidence")):
                finding("runtime_unverified", "runtime", "Scheduler health/online host not currently evidenced; configuration is insufficient")
            timestamp(runtime.get("observed_at"), "runtime", "observed_at")
            deadline(runtime.get("next_check_at"), "runtime", "runtime_overdue")
    return {"ok": not findings, "findings": findings,
            "limits": "Reported snapshot only; references and worker activity are not independently verified. No scheduler, repair or dispatch."}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True, help="Explicit private snapshot JSON; never scans project sources")
    args = parser.parse_args()
    try:
        result = check(json.loads(args.file.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object))
    except (OSError, ValueError, UnicodeError) as error:
        result = {"ok": False, "findings": [{"code": "unreadable_snapshot", "scope": "snapshot",
                                              "detail": type(error).__name__ + ": input unavailable or invalid"}]}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
