---
{"document":"documentation-refresh","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Documentation refresh proposals

[documentation_refresh.py](../../scripts/documentation_refresh.py) prepares dated candidate edits
and evidence in a version-1 private sidecar. An accepted task justifies this review; it does not
itself promote project truth. The helper never writes canonical pages, changes record status,
opens original materials, calls a model or publishes content. An agent/person authors replacement
passages after reviewing selected sources. The helper checks acceptance, hashes, routing and
inventory, not semantic truth. Keep hypotheses, unknowns, code/config facts, reviewed research and
runtime observations distinct.

```text
python -B scripts/documentation_refresh.py --root <project> propose --request .dreamdocs/refresh-request.json
python -B scripts/documentation_refresh.py --root <project> propose --request .dreamdocs/refresh-request.json --write
python -B scripts/documentation_refresh.py --root <project> check --proposal .dreamdocs/documentation-refresh/<id>.json
```

Default mode writes nothing. `--write` writes only an ignored private sidecar, using the common
writer lock, a second input-revision check, atomic publication and readback. Active/unresolved
locks or an active Dreamer run defer publication; locks are never removed. Exit 0 means a valid
proposal/check, **not** accepted docs. Exit 2 means unconfigured, invalid, stale, refused or
unavailable evidence. JSON is ASCII-escaped; no notifications or external reporting occur.

Publication requires an available Git worktree, an untracked destination and effective Git
exclusion of the exact sidecar path. Ignore-line presence is insufficient: later negations may
expose a file, and ignore rules do not protect tracked content. Existing owner rules are preserved;
ambiguous/unavailable exclusion or tracked destinations cause refusal before sidecar publication.
Non-Git projects can still preview proposals. This is a point-in-time check, not protection against
later owner changes or force-adds.

## Owner configuration and input

The owner maintains `.dreamdocs/documentation-policy.json`. Its exact fields are `version: 1`,
`project_id`, `manager`, `task_file` (a private project-relative snapshot under `.dreamdocs/`),
`allowed_targets` (exact documentation Markdown paths) and boolean `human_inventory`. For research,
allow the topic, `docs/status/current-state.md`, `docs/00-index.md` and category README. All proposed
routes must be allowed. Governance/AGENTS files cannot be targets. The helper never installs or
widens policy. It cannot interpret or override stricter prose rules: reconcile those with the
owner before configuring it. Root/category guidance and promotion rules are hashed and require
operator review.

The selected [task snapshot](task-continuity.md) must report `done`, matching immutable candidate,
independent approving review and configured Manager acceptance. Freshness/ordering are checked.
`candidate.source_hashes` must bind every selected source path to the SHA-256 revision accepted
with that candidate. Producers must supply this from actual review evidence; today's files, a
receipt, active episode, newer date or author PASS cannot supply acceptance. The snapshot is a
local producer report; external references are not independently authenticated. No tracker changes.

A request has exactly these fields:

- `version: 1`, `project_id`, `task_id`, `candidate`, `task_snapshot_sha256`, and one-line `title`.
- `sources`: 1–20 objects with `path`, `sha256`, `classification`. Classes: `code_fact`, `config_fact`,
  `runtime_observation`, `reviewed_research`, `episode`, `hypothesis`, `unknown`. Labels describe
  supplied evidence, not automatic truth attestations.
- `changes`: 1–20 objects with `path`, current target `sha256`, one-line `title`, selected
  `source_paths`, and bounded `before`/`after`. Existing targets need one unique old passage; new
  pages use `sha256: null`, `before: ""`. Author from approved sources with explicit unknowns.
- Boolean `human_inventory` and `dreamer_run_id` (normally `null`).

Sources/targets are at most 1 MiB; requests at most 128 KiB. Confined paths cannot cross links or
dependency trees. Originals, credentials, raw automation data and uncommitted Dreamer outputs are
refused as readable sources.

## History and recheck

The topic category README must be routed through `docs/00-index.md`. Candidate passages retain the
replaced passage as dated history. The helper proposes a dated pending current-state update unless
the request includes one, plus missing global/category links. Existing history/unrelated text
remain. Later reviewed research can propose replacing an obsolete draft claim while preserving
the earlier passage and exact source identities.

Sidecars record request hash, candidate/acceptance, classifications, source/routing/policy/snapshot
hashes, target before/after hashes and proposed text, date and review gate. Identical inputs reuse
the immutable sidecar; it is not active memory. `check` rebuilds it and detects changed, missing,
rolled-back or tampered sources/targets, acceptance, rules, inventory or proposal content. Recheck
before owner/area review and any separately authorized edit. There is no apply/promote command.
Changed input needs a new request/proposal; retain old evidence. Recall has no cache to invalidate.

For Dreamer input, bind the committed report to the accepted candidate. The run must equal
`state.last_run_id`, with successful report and matching episode snapshot hashes. Acceptance must
follow that completed result. Orphaned reports/proposals from failed finish, old checkpoints or
partial results cannot authorize refresh. Dreamer's existing result contract is unchanged.

## Human materials and public copies

With explicit policy/request scope, inventory covers only the selected `human-materials/` tree
(up to 10,000 entries) and its index. New names get proposed unread rows; stale rows become quoted
history. Reported `partial`/`unparseable` limits are preserved. Missing/stale names do not prove a
move. Unsafe links, inaccessible/incomplete inventory and invalid/duplicate rows stop preparation.
An empty selected tree does not prove absence of originals elsewhere.

Original bytes are never opened, hashed, moved, deleted, uploaded or force-added. Index status is
an assertion, not extraction proof; unchanged filenames do not prove unchanged content. Extraction
needs separate configured consent and an authorized reader with source identity/coverage evidence.
An approved extracted note may be a hashed source; this helper grants no original-reading consent.
Private index proposals/filenames stay in `.dreamdocs/`; do not commit or publish them by default.

Before public copying, run `python -B scripts/human_materials.py --root <export-root> --public-export`.
It rejects originals, populated indexes, malformed/incomplete inventory and private prose outside
the table. Only the shipped empty index (LF/BOM normalized) and no originals pass. Other exact
files/index content require a separate explicit owner decision and reviewed export workflow.
Ignore rules alone never authorize publication of tracked content.
