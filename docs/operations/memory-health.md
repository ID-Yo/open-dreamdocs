---
{"document":"memory-health","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Memory health

`python -B scripts/dreamdocs.py doctor` (also `status`) emits JSON and reads only.
Exit 1 means an unresolved gap, including unknown integration health; exit 2 means unavailable or
invalid input. Findings identify the component, next action, resume condition and next check.
No network reporting, background monitor, product start or scheduler installation occurs. Repeated
checks do not notify anyone; output is local. Missing observations never mean no work happened.

The report checks memory schemas, installed package hashes/version, client versions, all installed
hook definitions (including duplicates and moved paths), receipt/episode readback, queued and
leftover events, writer locks and Dreamer's checkpoint. Locks older than 15 minutes are **aged**,
not proven abandoned; neither default mode nor `--fix` removes them. Pending data older than 15
minutes needs investigation. After confirming writers stopped, use `memory reconcile` for pending
captures or a client SessionStart for leftover exact event files. Malformed/conflicting entries
stay available for inspection. Retry capture with the original identity, never repeat an uncertain
external task operation just to obtain a save.

Receipt readback proves bytes persisted, including manual captures. It does not prove trigger
delivery, client trust or fresh-session recall. Observations older than 24 hours are historical;
doctor asks for a new check rather than inventing current health. Scheduler/executor health remains
unverified until the separately authorized executor/scheduler work is implemented and observed;
filled schedule fields only report `configured_only`. Owner-paused work is never resumed.

`doctor --smoke` saves a unique synthetic value, reads it back and recalls it in a temporary isolated
project that is removed afterwards. It proves the local memory engine only. Synthetic episodes,
receipts and markers never enter project memory, install evidence or reusable facts. Client hooks
are not invoked by this smoke test. Actual client probes remain deliberate observed sessions; see
the [Codex](agents/codex.md) and [Claude Code](agents/claude-code.md) instructions and limitations.

## Explicit observations and task checkpoints

An owner/verifier can provide `--evidence <local-json-file>` with `version: 1` and `clients` keyed by
`codex` or `claude-code`. Each client can have independent `trust` and `recall` objects. Both require
`kind`, `observed_at` (timezone-aware, after install), `client_version`, `command_sha256`, `source`
(project-relative local report) and `sha256` of that report. Trust uses `kind: client-trust` and must
refer to actual observed client trust evidence. Recall uses `kind: fresh-session-recall` and also
requires `client`, `event_id`, `marker`, `capture_session` and a distinct `recall_session`. The marker
must occur in the acknowledged episode and the observed report. The report's identity, version,
source hash and age are rechecked each time. Doctor labels these **reported** observations: hashes
protect integrity, not authenticity or truth of a human-authored report. A receipt alone cannot
populate either observation. The [install schema](../../templates/install-manifest.schema.json)
defines the exact fields.

`--fix` persists only validated observation metadata and current capture-readback status in
`memory/automation/install.json`, under the normal writer lock. It does not repair user data,
rewrite hooks, grant trust or run clients. Without `--fix`, even supplied evidence is only reported.
Changed hooks/versions/sources invalidate prior claims; failed evidence remains unknown/pending.

`--checkpoints <local-json-file>` accepts an explicit array of objects with `task_id`, the exact
expected outcome `event`, `status` and `expected_at`. For due saves, it validates the task, project
and adapter identity and compares the full canonical event payload hash with a read-back receipt;
receipt ID membership alone is insufficient. Future checkpoints are not yet due. The report
reports `missing_save` when absent. Paused/backlog/future tasks are excluded. This does not discover
tasks, accept results or infer undocumented completions. Keep this checkpoint file private and
reconcile it with the authoritative tracker and [task continuity](task-continuity.md) snapshot.
