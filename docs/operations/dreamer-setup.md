---
{"document":"dreamer-setup","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Daily Dreamer Setup

This page describes the contract between a project's scheduler, runner and agent. The full policy is in [`memory/DREAMER_POLICY.md`](../../memory/DREAMER_POLICY.md). The file-based template does not create an active scheduler task or claim that the model's semantic judgments are correct.

## One owner and a daily schedule

Each project selects one scheduler owner, local timezone, local time and executor. The schedule runs once daily in the project's local time. Notifications cover failures, meaningful changes, completion or required action; unchanged state sends no message. Settings are recorded in `memory/config.json`:

```json
{
  "version": 1,
  "schedule": {
    "frequency": "daily",
    "timezone": null,
    "local_time": null,
    "owner": null
  },
  "review": {"episode_days": null}
}
```

`null` means the project has not configured the value yet. The file-based runner is included; the scheduler and its connection to the selected agent are configured externally. The package does not schedule work itself.

## First run

1. Fill in `PROJECT.md`, `AGENTS.md`, `docs/00-index.md`, `memory/README.md`, `memory/SCHEMA.md` and `memory/config.json`.
2. Select a scheduler owner and confirm the local timezone and time.
3. Run `python scripts/project_memory.py validate`.
4. Run `python scripts/project_memory.py begin`. The command acquires a lock, creates `memory/dreamer/work/RUN_ID/snapshot.json` and `result.json`, and prints the run ID.
5. The snapshot contains a complete manifest with hashes of all real input records and the contents of records changed since the last successful checkpoint or due/open. Canonical documents are read as needed and are outside the memory input manifest.
6. The agent reads the snapshot and initial `result.json`, then edits only `result.json`.
7. The agent fills in a valid `status`, nonempty `summary`, complete `reviewed_ids` on success and proposals following the result schema below. `memory/SCHEMA.md` describes Markdown memory records.
8. Run `python scripts/project_memory.py finish --run-id RUN_ID`.

Input records are not required: a zero-input run may finish with a short summary and empty `reviewed_ids` and `proposals`. Such a run does not require an automated model.

## Result schema

The initial file has `status: "pending"` and `reviewed_ids: []`. The agent deliberately changes it to `success`, `partial` or `failed` and provides a nonempty `summary`. For `success`, `reviewed_ids` must contain all snapshot IDs requiring review; for `partial` or `failed`, the summary describes what remains.

```json
{
  "run_id": "RUN_ID",
  "status": "success",
  "summary": "Brief run outcome.",
  "reviewed_ids": ["episode-001"],
  "proposals": [
    {
      "kind": "fact",
      "title": "Brief title",
      "source_ids": ["episode-001"],
      "body": "Proposal with scope and evidence."
    }
  ]
}
```

`kind` is one of `fact`, `procedure`, `contradiction`, `duplicate`, `archive`. A proposal is a review candidate, not an automatically active rule.

## Successful finish

`finish` checks the result schema, status, nonempty summary, allowed IDs and complete `reviewed_ids` on success. It also checks that the complete input manifest and snapshot hashes are unchanged: adding, editing or deleting a real record during the run causes failure without checkpoint advancement. After successful validation, the runner writes deterministic outputs:

- `memory/dreamer/reports/RUN_ID.json`;
- `memory/dreamer/proposals/ID.json`, where `ID` is a deterministic proposal hash.

The checkpoint advances only on `success`, after the report and proposals have been written. For `partial`, `failed` or interruption, the checkpoint stays at the previous successful run so the next `begin` retries the input. Generated reports and proposals do not become subsequent input.

## Concurrent runs, abort and recovery

- One lock permits only one run per project. A second `begin` stops with a conflict; locks are not automatically taken over.
- `python scripts/project_memory.py abort --run-id RUN_ID` releases the active run without advancing the checkpoint.
- `python scripts/project_memory.py recover --run-id RUN_ID --confirm-stopped --max-age-minutes N` explicitly recovers a confirmed stopped run. `N` must be positive. Use it only after checking that the process is actually stopped; the runner cannot prove this itself.
- Do not use `recover` to interrupt a live run or bypass a conflict.

## Daily procedure

The scheduler owner starts `begin` once daily. The agent reads the snapshot, fills in the result and calls `finish`. On error, preserve evidence and send a notification according to policy. When nothing has changed, the runner may complete with a zero-input result without notification. Generated files do not automatically trigger another run.

## Limitations

The runner checks structure, manifest, hashes and result shape. It does not prove that a proposed fact is true, that a skill is safe or that a semantic decision is correct. These decisions remain subject to owner review under [`docs/governance/`](../governance/README.md).

## Task execution is not scheduler configuration

The validator reports `scheduler_configured` when schedule fields are filled; it does not verify an installed scheduler, host availability or actual worker runs. Use [task continuity](task-continuity.md) for explicit external observations and durable handoff evidence. This runner and checker do not install or invoke a scheduler.
