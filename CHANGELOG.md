# Changelog

## Unreleased

- Added opt-in versioned task evidence snapshot/schema and a read-only continuity checker for actual-start, handoff, blocker, candidate/review acceptance and observed health/freshness gaps. Existing memory validation remains compatible; no scheduler or automatic dispatch is introduced.
- Added the automation lifecycle contract (#13): event schema v1, stable event and receipt identity, commit order, privacy classes, exit codes, project binding and rollback data rules, with a read-only event checker and fixtures. Codex and Claude Code remain unsupported until adapters are tested.
- Bounded validation to managed template files (#14): dependency, VCS, build and runtime folders and nested repositories are skipped before listing, links and junctions in managed folders and unreadable folders fail visibly, and the portable copy test uses an explicit size-limited file list.
- Added `scripts/dreamdocs.py memory capture` and `reconcile` (#16): checked outcome events become an episode plus receipt with readback, replay is idempotent, captures queue under the writer lock shared with Dreamer, and failures never report saved. Includes the outcome event schema and README files for the new automation folders. No client adapter calls it yet.
- Added `scripts/dreamdocs.py memory recall` (#17): deterministic, read-only selection of accepted facts and procedures, open contradictions and labeled recent episodes for one project, with rehashed source status and a bounded context block framed as untrusted data. Distinguishes ok, no match, empty and unavailable. No client adapter calls it yet.
- Added the Codex hook adapter (#18): `adapters/codex/hook.py` recalls memory at `SessionStart` and for meaningful prompts, saves each turn at `Stop` from an optional `dreamdocs-outcome` block (receipt only without one), publishes queued captures at `SessionEnd`, never blocks the agent, reads no transcript and calls no model. Tested with recorded Codex 0.147.0 payloads; not yet verified end to end with trusted hooks.

## v1.4.0

- Added the approved eight-label JSON baseline and a dry-run-first import procedure with explicit workflow authority; no existing repository labels are changed automatically.
- Added five independent Marketing fields with selective topic routing.
- Added empty Human Materials scaffolding, a recursive index procedure and a
  read-only coverage checker with explicit private/public-copy boundaries.
- Added a once-per-adoption optional Codex Bot Mode offer (Yes / No / Skip)
  and safe merging guidance; no companion is installed automatically.
- Added scoped AGENTS guidance beside the README in every documentation category.
- Preserved canonical governance, private-material boundaries and independent use.


## v1.3.0

- Translated all public guides, templates, examples, prompts and documentation into English.
- Updated the README to reflect the English-only release.
- Preserved folder structure, record metadata, governance rules and runner behavior.

## v1.2

- Unified 13 pre-created categories into a canonical `docs/` structure.
- Added a short root entry point, selective routing and clear core/optional markers.
- Retained the previous version's fillable architecture, product, operations and current-state sections.
- Centralized authority, lifecycle and promotion rules in `docs/governance/`.
- Documented daily Dreamer processing from the last successful checkpoint, including snapshot, result, lock and recovery.
- Separated templates and examples from active memory and excluded them from retrieval.
- The package does not activate a scheduler; each project configures its own daily schedule.
