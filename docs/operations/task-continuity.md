---
{"document":"task-continuity","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Verifiable task continuity

Use the optional [task snapshot](../../templates/task.json) and
[version 1 schema](../../templates/task.schema.json) when a project needs a durable,
machine-readable checkpoint alongside its authorized GitHub issue tracker. Follow
[GitHub issue before actionable work](../governance/task-intake.md) before execution;
local memory, ledgers and this snapshot are supplementary evidence and a temporary
offline pending-sync queue, not a local-only tracking mode or permission to resume
paused work. During an outage, retain a stable pending-sync ID and disclose that
it is unpublished; reconcile it to the matching GitHub issue without duplicates.
Keep task snapshots private unless the exact content is approved for publication.
The reusable template contains no real tasks or runtime observations.

## Existing capability and limit

The memory validator checks record/configuration/link integrity. Its
`scheduler_configured` value only means schedule fields are filled in; it does
not inspect an installed scheduler, host uptime, model capacity or worker turns.
The Dreamer runner processes memory snapshots when explicitly invoked. Neither
that runner nor this task checker schedules or dispatches team work. An operating
rule alone cannot ensure execution while the host is offline or no observer runs.

```text
python -B scripts/task_continuity.py --file <private-snapshot.json>
```

The checker reads only the explicitly named JSON file, writes no state and makes
no network calls. Exit 0 means no snapshot discrepancies were found; exit 1 means
findings, unavailable input or malformed JSON. JSON output has `ok`, `findings`
(`code`, `scope`, `detail`) and a limits statement. Never interpret exit 0 as
independent proof of source truth or live execution. Missing input fails closed;
it does not mean zero tasks. An explicit empty array is an observer's assertion
of zero tasks, not discovery of the tracker. Existing memory schemas are unchanged.

## Durable producer contract

The existing Manager or runtime adapter reconciles the authorized GitHub issues and
fresh roster into the snapshot. Preserve bot identity mapping, owner pauses and
history. Do not select github/local/both execution modes; local evidence always
supplements GitHub, except for the temporary pending-sync path during an outage.
Without an authorized GitHub destination, record a setup blocker and proceed only
with independent authorized work. Record `reconciled_at` and the concrete
`next_check_at`.
The producer must write the complete JSON atomically (temporary file then replace),
preserve its last known good checkpoint and serialize writers. This checker never
repairs, advances, merges or resubmits a handoff after interruption.

Each task has stable `id`, `manager`, current `executor` (or null), `status`,
explicit `start_approved`, `next_action`, `acceptance`, source `evidence`,
`updated_at`, `next_check_at`, ordered `handoffs`, and nullable `blocker`,
`candidate`, `review`, `accepted`. Time values include timezone. Evidence strings
are references, not secrets, raw logs, personal information or hidden reasoning.
Include the authorized GitHub issue reference in task evidence, or the disclosed
stable pending-sync ID during an outage, then reconcile it when service returns.
The checker does not fetch references or enforce the intake policy. The producer
must verify their actual identity and contents; a nonempty string is not a truth
attestation.

For [documentation refresh](documentation-refresh.md), the producer additionally records
`candidate.source_hashes`: selected project-relative source paths and SHA-256 revisions reviewed
and accepted with that exact candidate. This optional extension leaves v1 continuity checks
unchanged and grants no promotion. Refresh requires it and rejects absent or stale bindings.

- A handoff records unique `id`, `worker`, `stage` (implementation/review/qa/
  integration), `requested_at`, `acknowledged_at`, `started_at`, `finished_at`
  and evidence. Nullable timestamps mean not yet observed. Request, acknowledgment,
  actual activity and finish are different events and must be chronologically
  nondecreasing; equal timestamps may reflect clock precision, not equivalent
  events. Persist
  the request before sending; reconcile an uncertain send before retrying.
- Before ending a turn, the Manager inspects the actual result and verifies a
  successor has started, or records `status: blocked` and reason, unblock `owner`,
  `resume_condition`, `next_check_at` and evidence. Finished stages without an
  actual successor, dispatch/ack without start and mismatched current executor
  are findings. Capacity/dependency waits are explicit blockers. One snapshot
  task represents one current stage; split genuinely parallel independent tasks.
- `backlog`, `paused` and `future` remain excluded from execution requirements.
  `ready` without start approval does not require worker activity. Approval to
  start ready work does. Do not turn a policy audit into a product restart.
- `done` requires immutable `candidate.id` and `author`, independent
  `review.reviewer` (different from author), `verdict: approve`, matching candidate,
  review time/evidence and matching Manager acceptance identity/time/evidence.
  Candidate can be a commit or a bounded local manifest digest linked from the
  issue; offline acceptance evidence remains unpublished until reconciled. Do not
  imply remote integration/publication from local evidence. Author PASS or a delivery
  receipt cannot satisfy this gate. The producer verifies the reviewer belongs
  to the intended role; different strings alone cannot establish independence.

## Freshness, health and reconciliation

Reconciliation/task/blocker/runtime deadlines are explicit per-project choices;
there is no universal timeout. A deadline at or before the check time is overdue.
Task updates newer than reconciliation are flagged. Timestamp ordering prevents
future observations; it does not prove an observation was truthful or complete.
Choose short next checks appropriate to a worker turn, not a distant deadline to
hide a stopped stage. The producer must expire/reconcile worker activity and never
carry an old `started_at` forward as proof of a currently running turn.

`runtime` carries external `scheduler` observation (healthy/unhealthy/unknown/
not_configured), `host` (online/offline/unknown), `observed_at`, `next_check_at` and
evidence. Started approved work with unknown, absent, offline, unhealthy or overdue
observations is not green. Blocked tasks still need visibility, while paused/
backlog/future tasks never demand execution. Scheduler configuration alone cannot
set healthy. An external observer must check actual runs/heartbeat and host state.
No observation means unknown, not an outage diagnosis. Installing a scheduler or
changing it requires the project's existing authority and an actual runtime plan.

After power loss, read the durable request, actual worker/remote outcome and
checkpoint before any resend. Reconcile the exact candidate and fresh review
identity before acceptance. Report discrepancies to the responsible Manager/COS;
this read-only checker performs no intervention and cannot guarantee continuous
work between observations. Integrations must preserve owner pauses, privacy and
conflict-free writes. A checker that is never invoked cannot enforce this contract.

The [CBM ownership policy](https://github.com/ID-Yo/codex-bot-mode/blob/82b14882f2f8bf5c1276c227a2a70022dffb083f/docs/operations/task-ownership-and-follow-through.md)
describes role duties; use this snapshot for explicit evidence checks. A runtime
adapter must map its real worker/scheduler facts to these fields rather than
claiming compatibility from a policy link alone.
