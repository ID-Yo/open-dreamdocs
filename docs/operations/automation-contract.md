---
{"document":"automation-contract","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Automation lifecycle contract (v1)

This page defines the shared contract for automatic project memory in Codex and
Claude Code. It is the reference for setup, capture, recall, adapters, health and
upgrades. **No part of this package captures or recalls automatically yet.** The
executable part today is a read-only event checker:

```text
python -B scripts/automation_contract.py --root . --event EVENT.json
```

It validates one event, prints the decision and planned identifiers, and writes
nothing. Machine-readable cases live in [tests/fixtures/automation](../../tests/fixtures/automation/).

## Lifecycle

```text
approved setup -> relevant recall -> task outcome event -> durable episode/receipt
-> readback -> bounded curation -> sourced proposals -> reviewed acceptance
```

Automatic capture may create an episode and a receipt. Active facts, skills,
accepted decisions and canonical documentation still follow
[promotion rules](../governance/promotion-rules.md). A finished coding turn is not
a finished project task: the event reports the task status separately.

## States are separate claims

| State | Meaning | Evidence required |
|---|---|---|
| configured | Binding and settings files exist and validate | Validator output |
| trusted | The client accepted the project and its hook/command definition | Client trust record or prompt approval |
| installed | Adapter files are present for an exact client version | Setup manifest (#15) |
| triggered | The client actually invoked the adapter for a real event | Adapter log entry with event ID |
| persisted | Episode and receipt were written and read back | Receipt with matching hashes |
| recalled | A fresh session received relevant records | Recall receipt (#17) |
| healthy | Recent expected events have receipts; nothing is missed or overdue | Doctor report (#22) |

No state implies a later one. A config file or a setup success message proves only
"configured". When the host or client is stopped, health is unknown.

## Client support

Observed 2026-10-22 on Windows 10.0.26100: codex-cli 0.147.0 and Claude Code
2.1.273 are installed. No adapter has shipped or been tested, so both clients are
**unsupported**. The checker's `SUPPORT` table carries the same values, and
`automatic` stays false until an entry is `tested` with client version, OS,
surface, test date and evidence. Every other combination is unsupported.

| Client | Lifecycle hooks | Trust requirement | Status |
|---|---|---|---|
| Codex | `SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd` fired in a throwaway probe of 0.147.0 on Windows, run with the trust bypass flag; `SessionEnd` timeout is clamped to 3 s | Untrusted or changed hooks are skipped; setup and every upgrade include an explicit review and trust step | unsupported |
| Claude Code | `SessionStart` and `UserPromptSubmit` fired in a 2.1.273 probe; a failed turn fired `StopFailure`; `Stop` and `SessionEnd` (1.5 s default budget) are unverified | Hook definitions are reviewed in the client; changed hooks need new review | unsupported |

Probe results show client behavior and are not product support. Windows is a
required acceptance target for both clients. Adapters follow four rules:

- `Stop` is the durable save point. `SessionEnd` may only run a fast, idempotent
  finish for an event already saved at `Stop`.
- Claude Code `StopFailure` is non-durable: the adapter reports the outcome as
  `interrupted`, so nothing is written and the same identity is redelivered later.
- Setup, upgrade and acceptance runs never use `--dangerously-bypass-hook-trust`
  or an equivalent bypass.
- Hook commands call an absolute Python interpreter path with arguments and do not
  depend on a particular shell (Git Bash, PowerShell or cmd).

**Auth and cost.** Validation and persistence are deterministic local Python with
no network or model calls. Extraction that needs judgment uses the already
authenticated agent session that produced the work; no separate paid model API,
cloud service or embeddings are required. Events are bounded: summary 2000
characters, at most 10 lessons of 600 characters and 20 evidence references.

**Degraded modes.** Missing binding or an adapter absent from the binding returns
`degraded` (exit 4): capture is manual and must not be called automatic. A hook
that never fires leaves no receipt; only the doctor (#22) can report it as missed.

## Event schema v1

All fields are required and no others are allowed.

| Field | Value |
|---|---|
| `version` | `1` |
| `kind` | `session_start`, `task_start`, `task_outcome`, `session_end` |
| `adapter` | `codex` or `claude-code` |
| `session_id`, `turn_id` | Client session and turn, or task revision |
| `project_id`, `worktree`, `agent` | Must match the installed binding; prevent cross-project leaks |
| `occurred_at` | Timestamp with timezone |
| `privacy` | `public`, `project`, `restricted`, `prohibited` |
| `task` | `null` or `{id, status}` with backlog/ready/in-progress/review/blocked/paused/done |
| `outcome` | Only for `task_outcome`: `{status, summary, evidence, lessons}`; otherwise `null` |

Outcome status is `success`, `no_lesson`, `partial`, `failed` or
`interrupted`. Evidence uses the memory source prefixes `id:`, `file:`,
`https://`, `ref:`; captured outcomes need at least one. Lessons are plain text;
an event cannot set record status, owner or acceptance.

## Identity, receipts and readback

- `event_id` = `evt-` + first 32 hex characters of SHA-256 over the canonical JSON
  of adapter, session_id, turn_id, kind, project_id, worktree and agent.
- `payload_sha256` = SHA-256 of the canonical JSON of the whole event.
- Episode path: `memory/episodes/auto-<event_id>.md`; receipt path:
  `memory/automation/receipts/<event_id>.json`.
- Receipt v1 is a JSON object with exactly `version`, `event_id`, `payload_sha256`,
  `decision`, `outcome`, `status` (`persisted`, `receipt_only`, `reject` or
  `invalid`), `episode`, `episode_sha256` and `recorded_at`. Any other shape or
  version is `invalid` (exit 2), never retryable.

Commit order for a writer (#16):

1. Check the event. Only exit 0 decisions write anything.
2. Take the writer lock `memory/dreamer/command.lock`, which Dreamer commands also
   use. It records the owner process and acquisition time. If it is held or a
   Dreamer run is active, queue the checked capture as pending (exit 1); never
   remove another writer's lock.
3. Render the episode deterministically from the event (no write-time values) and
   create it atomically. If the file already exists, identical bytes continue;
   different bytes are a conflict.
4. Read the episode back and hash it.
5. Write the receipt atomically, read it back and compare hashes.
6. Release the lock and only then report success.

A crash after step 2 and before step 3 leaves only the lock. Captures then queue
as pending until the lock is recovered: nobody takes it over automatically. After
confirming that the recorded owner process has stopped, the operator removes only
that lock, as for Dreamer, and the doctor (#22) reports locks older than its
threshold. A crash between 3 and 5 leaves an episode without a receipt, and
redelivery completes the receipt after comparing bytes. A crash after step 5
becomes a `duplicate`. Concurrent duplicate deliveries produce identical bytes;
the same identity with a different payload is a `conflict`.

Redelivery uses exact bytes. Before the first delivery, an adapter writes the
event file and then redelivers only that file. `payload_sha256` covers every
field, so an event rebuilt later (for example with a new `occurred_at` at
`SessionEnd` or after `StopFailure`) is a `conflict` by design.
Worktrees of one project write the same deterministic files, so Git merges equal
events cleanly and shows different ones as conflicts.

## Privacy classes

| Class | Handling |
|---|---|
| public | May be captured and later published after review |
| project | Captured in project memory; never exported without review |
| restricted | Receipt only; no episode content |
| prohibited | Rejected before any write |

Credential-like content is rejected regardless of class. Privacy labels do not
authorize raw transcripts, personal data or private originals.

## Decisions and exit codes

| Exit | Decision | Meaning |
|---|---|---|
| 0 | `capture_episode`, `receipt_only`, `recall_only`, `duplicate` | Allowed; duplicate is an idempotent replay |
| 1 | `retry_pending`, or capture of a `partial`/`failed` outcome | Recorded or pending; never a success checkpoint |
| 2 | `invalid` | Malformed event, binding or receipt, or an unknown future version |
| 3 | `reject` | Foreign project, prohibited class or unsafe content |
| 4 | `degraded` | Not installed for this project or adapter; manual only |
| 5 | `conflict` | Same identity, different payload |

Paused tasks produce `receipt_only` or `recall_only`. No event authorizes
resuming paused work or promoting records; every result reports
`resume_authorized: false` and `promotion: review-required`.

## Project binding, compatibility and rollback

Setup (#15) creates `memory/automation.json`:
`{"version": 1, "project_id": "...", "adapters": ["codex", "claude-code"]}`.
The template ships without it, so a fresh download is not installed. The binding
is a separate file because `memory/config.json` v1 rejects unknown keys in
current and older validators; it stays unchanged so a rollback keeps validating.

Unknown binding, event or receipt versions fail visibly with exit 2 and are not
migrated. Upgrades (#23) replace only package-managed files. User documentation,
original materials, memory records, receipts and the binding are user data:
rollback restores package files and compatible configuration without restoring an
old memory snapshot or deleting records or receipts created after the upgrade.

