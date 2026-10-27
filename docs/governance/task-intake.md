---
{"document":"task-intake","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# GitHub issue before actionable work

Every actionable task, change, bug or decision must link to an existing GitHub
issue, or get a new issue, **before execution starts**. This includes non-code
work, reviews and verification. A local ledger, memory record or task snapshot
supplements the issue; it is not a local-only execution tracker. The project
Manager owns intake, assignment, state and completion. Creating an issue does
not grant start approval, publication rights or permission to spend.

## Reuse and exceptions

Search the authorized project tracker first. Reuse a matching existing issue or
parent issue and record the bounded scope/stage there. Do not create an issue
per message, test command, handoff or executor stage. Use a linked child issue
only when work needs independent ownership or acceptance criteria. Recurring
approved work may reuse its issue reference; individual receipts are evidence.

Conversation and short read-only questions are exceptions. If either becomes
actionable work, link or create its issue before executing that work. Do not
rewrite historical task statuses or priorities, or create retroactive issues.

## Authorized destination and privacy

Confirm the project's authorized GitHub repository and its visibility before
publishing. Never publish private content to an unrelated or public tracker.
Use an authorized private repository for private work; publish only privacy-safe
outcome/scope/evidence references. Do not put secrets, personal data, private
originals or raw logs in issues, comments or local task records.

A project without an authorized GitHub destination records a **setup blocker**:
reason, unblock owner, resume condition and next check. Report it to the Manager
and continue only independent, authorized work that has its own valid issue or
qualifies for the conversation/read-only exception. A local-only mode is not a
substitute for an authorized destination. Resolve destination and visibility
with the owner before the dependent work proceeds.

## GitHub unavailable: pending sync

When GitHub is unavailable and the project has an authorized destination,
immediately write a local **pending-sync task record before execution**. Include
a stable ID, goal, scope, acceptance criteria, owner, state and evidence, plus
the authorized destination and known issue reference when available. Disclose
to the requester that it is **not published yet**. Keep the record private.
This temporary outage path permits only already authorized work within the
recorded scope; it grants no additional authority.

When GitHub is back, search for the matching issue/parent and stable ID before
creating anything. Reconcile the pending record and stage evidence into that
issue without duplicates, and record its link locally. If an earlier write may
have succeeded, read back its result before retrying. Do not claim a local record
is published or replay uncertain external actions to obtain tracker evidence.
An outage queue is temporary supplementary evidence, not a selectable local mode.

## Issue contents and state

Before dispatch, the issue must state:

- Intended outcome, bounded scope and verifiable acceptance criteria.
- Responsible Manager and executor (or explicitly unassigned before dispatch).
- Exactly one approved task-state label. Set the work type (`type:epic`,
  `type:story` or `type:task`) only when it is clear. Never guess.
  An unclear type does not block creating the issue. Follow the
  [approved label definitions and rules](../operations/github-labels.md).
- Priority only when explicitly chosen; normal has no label. Priority never
  grants approval to start or changes dependencies, state or blocker requirements.
- Explicit start approval, next responsible participant and next concrete action.

Each stage posts a stage completion record on the same issue: task ID and stage,
worker identity, result, evidence with exact candidate SHA and author where
applicable, checks/limits, and proposed next responsible participant/action.
The Manager dispatches successors and reconciles actual start and completion
using [task continuity evidence](../operations/task-continuity.md). A blocked issue
must record reason, unblock owner, resume condition and next check; use needs-owner
only when the owner must act. A stage result is not whole-task acceptance.
Intermediate/feature PRs use `Refs #N`; the Manager owns completion and closure.

Local memory, ledgers and snapshots retain lessons, provenance and continuity
evidence or the offline pending-sync queue. They do not replace the GitHub issue
or prove execution, acceptance or publication on their own. Updating installed
project profiles is a separately coordinated adoption step, not an automatic
effect of changing this template.
