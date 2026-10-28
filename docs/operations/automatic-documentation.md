---
{"document":"automatic-documentation","status":"draft","owner":"<project-owner>","last_reviewed":"2026-10-28"}
---

# Automatic documentation

[ADR-0001](../decisions/ADR-0001-automatic-documentation.md) defines the three documentation tiers.
This page describes tier A and docs debt.

## Tier A: status written from saved outcomes

After each saved outcome, the Stop hook runs `docs sync`. Session start runs it as well.

- `docs/status/activity-log.md` gets one line per saved outcome: time, status, task and reported
  state, the summary and up to three pieces of evidence. Lines carry the event ID, so a redelivered
  turn is never logged twice.
- `docs/status/current-state.md` gets one generated block between
  `<!-- dreamdocs:recent:start -->` and `<!-- dreamdocs:recent:end -->`. It holds the latest
  ten outcomes and every task whose latest reported state is not `done`. The page and markers are
  created when missing. Incomplete or duplicated markers are refused and reported; the page is left alone.
- Turns without an outcome block (`no_lesson`) and receipt-only outcomes write nothing.
- The sync uses the shared writer lock. When the lock is busy, the next hook catches up.

A new activity log starts one day back. To backfill older saved outcomes, run:

```text
python -B scripts/dreamdocs.py docs sync --since 2026-10-01
python -B scripts/dreamdocs.py docs status
```

## Docs debt

Session start records the current commit and a fingerprint of every uncommitted entry. At each Stop, the
hook compares against that observation: new commits and uncommitted entries that changed since then.
Code changed with no `docs/` page changed records debt in `.dreamdocs/docs-state.json`; work that
was already uncommitted before the session is not counted. Session start
and doctor show it. Debt clears when a docs page changes, or when the outcome block says
`"docs_impact": "updated"`. Use `"docs_impact": "none"` for changes with no documentation effect.
Files under `memory/`, `.dreamdocs/`, `.codex/`, `.claude/`, `human-materials/` and Markdown files are not code.

## Limits

Generated lines are the agent's report, not verified truth. Tier A never edits topic pages, governance,
decisions or memory records. Doctor reports `docs_status_missing`, `docs_status_stale` and `docs_debt`.

