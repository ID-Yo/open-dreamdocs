---
{"document":"dreamer-execution","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Explicit Dreamer execution

No executor or scheduler is active by default. The [legacy runner](dreamer-setup.md) still supports
manual begin/result/finish; [dreamer_executor.py](../../scripts/dreamer_executor.py) adds explicit
executor identity, budgets and execution/readback evidence. Keep memory/config.json at version 1.
The owner separately configures private `.dreamdocs/dreamer.json`:

```json
{
  "version": 1,
  "project_id": "your-project-binding",
  "paused": false,
  "evidence_files": ["docs/governance/promotion-rules.md"],
  "executor": {
    "id": "project-operator",
    "kind": "operator",
    "argv": null,
    "timeout_seconds": 3600,
    "max_records": 100,
    "max_input_bytes": 1048576,
    "max_result_bytes": 1048576,
    "max_proposals": 20
  },
  "scheduler": null
}
```

The project ID must match memory/automation.json. Missing/null executor reports `unconfigured`;
owner pause, wrong identity, unavailable command, capacity/budget or lock conflict reports blocked.
No installed client, subscription credential, transcript or hook trust is assumed to authorize
model access. Auth/capacity denial must be reported by the selected executor as failure/partial;
the wrapper cannot independently authenticate a result's semantic claims.

Keep this configuration and runtime receipts private. A missing .dreamdocs/.gitignore is created
with `*`; existing rules are preserved. In Git worktrees, tracked configuration/receipt paths or
ineffective exclusion (including negation overrides) block publication/execution receipts. Review
and fix those rules explicitly. Non-Git local execution has no Git exclusion guarantee if someone
later adopts the folder into a repository; review the complete private inventory before doing so.

## Operator workflow

```text
python -B scripts/dreamdocs.py dreamer begin --executor project-operator
python -B scripts/dreamdocs.py dreamer start --run-id RUN_ID --executor project-operator
```

`begin` prepares a snapshot and private receipt with `started_at: null`; preparation is not actual
work. The operator calls `start` immediately before reviewing the snapshot and writes only its
work/RUN_ID/result.json, using the [result contract](dreamer-setup.md#result-schema). Then:

```text
python -B scripts/dreamdocs.py dreamer finish --run-id RUN_ID --executor project-operator
python -B scripts/dreamdocs.py dreamer status
```

Receipts record project/root/run/executor, request/preparation/start/finish times, budgets,
config/snapshot/result/report/proposal hashes and checkpoint readback. Operator timestamps are
explicitly reported, not independently detected worker activity. Only exact validated success,
report readback and matching state.last_run_id/source manifest count as committed success.
Reports or orphan proposals from failed finish cannot qualify. Partial/failed/malformed/stale or
over-budget results preserve the old checkpoint. Keep failed work for correction or explicit
stopped-run abort/recovery; no active facts, skills or canonical docs are promoted.
Explicit recovery after a host crash, offline interruption or abandoned lock uses
`python -B scripts/dreamdocs.py dreamer recover --run-id ID --max-age-minutes N --confirm-stopped`
(or `scripts/project_memory.py recover`). It requires `confirm-stopped` and a positive age threshold,
releases the lock without advancing checkpoint, and marks the recovered run failed in reports.

Manual and scheduled `dreamer run` receipts also retain the Human Materials step's
state, trigger, finish time and counts under `materials`; filenames, content and raw
errors are excluded. This summary is covered by the receipt's existing readback hash
and shown by `dreamer status` and `doctor`. Later indexing does not replace it, and
indexing failure does not block curation. Legacy receipts and the separate operator
begin/start/finish workflow have no indexing summary and show `materials: null`.

Selected evidence_files, root rules/promotion policy, config/binding and local file sources in
snapshot records are hashed and rechecked inside finish. List any additional reviewed local sources
explicitly. Originals/credentials are refused; original reading requires a separate consented
reader and extracted notes. Remote/nonretrievable references remain operator-reviewed. Neither
the wrapper nor result schema proves semantic truth or sandboxes a trusted executor's filesystem.

## Selected command executor

For a preapproved local command, set kind to `command` and argv to an array beginning with an
absolute executable. Arguments can contain `{project}`, `{run_id}`, `{snapshot}`, `{result}`.
`dreamer run --executor ID` starts that exact argument-form process without a shell. It must read
the snapshot and write only that result. No model call is implicit. stdout/stderr are discarded,
not saved as raw transcripts. PID, exit and timeout are observed before result validation/finish.
Do not put credentials in argv/config; authentication belongs to the selected authorized executor.

Timeout closes the owned Windows kill-on-close Job (POSIX process group elsewhere) and joins its
process before aborting its own run. Uncertain Job attachment/cleanup retains the run lock for
inspection. A small launch-to-Job-attachment interval means this is cooperative process management,
not hostile-code containment. Never take over live locks. An interrupted finish retains proposed
outputs/work without claiming checkpoint success. Status rechecks evidence rather than trusting
the existence of a success report.

## Separate Windows scheduler opt-in

Manual execution installs no task. To opt in, select a verified command executor, fill in the
existing v1 schedule fields (owner equals executor ID), and configure:

```json
{"backend":"windows-task-scheduler","enabled":true,"windows_user":"DOMAIN\\user"}
```

as the scheduler property in .dreamdocs/dreamer.json. Then preview before explicit installation:

```text
python -B scripts/dreamdocs.py dreamer schedule install
python -B scripts/dreamdocs.py dreamer schedule install --apply
python -B scripts/dreamdocs.py dreamer schedule status
python -B scripts/dreamdocs.py dreamer schedule disable --apply
python -B scripts/dreamdocs.py dreamer schedule remove --apply
```

Review the exact project/task/root, executable/arguments/cwd, account, zone/time and timeout.
Project zone must match host timezone/DST; otherwise installation refuses. The task uses current
interactive logon, least privilege, no stored password, no wake or desktop/security bypass.
An owner must be logged in; an offline/powered-off host cannot execute. StartWhenAvailable permits
catch-up when available. IgnoreNew and shared command/run locks prevent overlap. One consolidated
run covers inputs since the last successful checkpoint; missed days never cause a replay burst.

Existing tasks require matching local identity and operational XML. Duplicate/changed/moved or
unowned tasks are conflicts, never overwritten. Changed configuration requires review/reinstall.
Explicit disable/remove still works after owner pause or executor removal, but refuses running/
queued work and preserves memory. Repeat install does not re-enable a disabled task. Root task
inventory covers Dreamdocs candidates, not arbitrary unrelated scheduler folders.

Configured, installed, actual trigger, executor result and checkpoint are distinct. Installed
without observations is `installed_unobserved`. Observed success requires a recent successful
execution receipt/checkpoint/readback plus live scheduler last-invocation time/result. The scheduled
CLI flag alone is not service evidence. Stale/denied/offline/unknown observations never synthesize
success. No external notifications are sent; unchanged not-due checks remain quiet. Real installation
and trigger/executor acceptance must follow owner opt-in; backend simulations or a read-only COM
query do not prove that acceptance.
