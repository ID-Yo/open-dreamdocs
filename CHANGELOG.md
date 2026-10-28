# Changelog

## v1.6.0-rc.4 — 2026-10-28 (candidate; pilot rollout)

- A file cited by an existing memory record may later move or be deleted (a branch switch, a cleaned-up report) without blocking validation, Dreamer or every later capture. `validate` lists it as a warning and recall marks it missing. New captures still check their evidence (found in the pilot).

## v1.6.0-rc.3 — 2026-10-28 (candidate; pilot rollout)

- Docs debt counts only changes made since the previous observation (session start or the previous turn). Uncommitted work that existed before the session is no longer reported as debt (found in the pilot).

## v1.6.0-rc.2 — 2026-10-28 (candidate; pilot rollout)

- Docs debt is also tracked in a Git repository that has no commits yet (found in the pilot).

## v1.6.0-rc.1 — 2026-10-28 (candidate; pilot rollout)

- Status documentation now updates automatically ([ADR-0001](docs/decisions/ADR-0001-automatic-documentation.md)). Every saved outcome adds a line to `docs/status/activity-log.md` and refreshes a generated block in `docs/status/current-state.md`; owner text outside the markers is preserved byte for byte. `dreamdocs.py docs sync --since DATE` backfills older outcomes.
- A code change without a documentation change is reported as docs debt at session start and by `doctor`. The outcome block accepts `docs_impact` (`updated`, `none`, `needed`).
- Capture no longer refuses a whole outcome because of evidence it cannot verify here (a file in another branch or outside the project, or `id:` used for a commit or task number). Such evidence is kept as `ref:` with the reason.
- `memory redeliver` retries every unsaved turn; session start and `doctor` name unsaved turns and their cause, and `doctor` reports a binding/record project ID mismatch.
- `validate` now only warns about missing READMEs outside `memory/`.

## v1.5.0-rc.6 — 2026-10-25 (candidate; release gates pending)

- Scheduled Dreamer runs on Windows can now summarize Human Materials: when Codex was installed from the Codex desktop app, its CLI lives in the app's virtualized AppData and is not on PATH for Task Scheduler. The summarizer now also looks in the desktop app package folder.

## v1.5.0-rc.5 — 2026-10-25 (candidate; release gates pending)

- Upgrades and rollbacks of real projects no longer stop at "interrupted" because project folders under `docs/` lack a README. The commit gate now checks only what Dreamdocs needs to run (config, memory records, Dreamer checkpoint); `project_memory.py validate` still reports documentation style findings.

## v1.5.0-rc.4 — 2026-10-25 (candidate; release gates pending)

- Fixed upgrades of projects set up with 1.5.0-rc.1/rc.2: setup had recorded project-owned files under `scripts/` and `adapters/` (for example `scripts/build-release.ps1`) as package files, and upgrade then refused the whole manifest. Upgrade now ignores such entries, never deletes a file the new package does not ship (`retained_not_in_package`), and setup records only package-type files that the package actually ships.

## v1.5.0-rc.3 — 2026-10-25 (candidate; release gates pending)

- Added automatic Human Materials indexing (epic #29). With owner consent (`dreamdocs.py materials mode inventory|summarize`, default `off`), every session start (background, at most every 6 hours) and every Dreamer run hashes `human-materials/`, keeps index rows in sync for new, moved and removed files, and in `summarize` mode asks an isolated read-only Codex run for a summary, tags, category and sensitivity written as `ai-draft` rows. Human-reviewed rows are never overwritten; changes to them become proposals. Privacy patterns, owner excludes, size limits and credential checks keep files away from the model.
- Text, DOCX, PPTX, XLSX and OpenDocument extraction uses the standard library; PDF uses optional `pypdf` or `pdftotext`; images are attached; other formats are marked `unparseable`.
- Recall now offers matching material summaries (and a count at session start) so agents open originals only when needed. `doctor` reports indexing mode, pending files and review proposals.
- Fixed Windows Task Scheduler readback (#21): principals are compared by SID, durations are normalized, and defaults omitted by Windows are filled in. A matching task left by an earlier failed readback is adopted instead of refused.

## v1.5.0-rc.2 — 2026-10-24 (candidate; release gates pending)

- Fixed external setup preview reading a missing target outcome block; the reviewed package supplies the preview template. Empty or incomplete existing owner blocks are conflicts, and valid custom blocks are retained.
- Setup preview/apply now refuse missing target runtime assets without writes, listing prerequisites instead of claiming installation with broken hooks. Documented fresh ZIP extraction and selective adoption before setup.
- Claude authentication, daily scheduling and broader client support gates remain unchanged.

## v1.5.0-rc.1 — 2026-10-22 (candidate; release gates pending)

- Added project-scoped Codex and experimental Claude Code setup/uninstall, versioned install manifests, exact instruction-block merging and machine-local hook settings. No global client configuration is changed.
- Added validated lifecycle events, durable capture/readback, exact replay and queued/redelivered outcomes with shared Dreamer locks. Private events/pending data stay local; receipt retention is owner-controlled.
- Added bounded deterministic recall with source hashes and untrusted-context framing. Templates/proposals/foreign projects never become accepted facts.
- Added doctor with distinct capture, hook integrity, reported trust and fresh-session recall provenance; isolated smoke tests never create active lessons. Missing runtime evidence remains unknown.
- Added private source-bound documentation/status/index proposals with immutable hashes, independent acceptance and owner promotion gates; material inventory remains coverage-only with strict public-export checks.
- Added explicit operator/command Dreamer execution, budgets, process cleanup, report/checkpoint readback and separately opted-in Windows scheduling. Configured, installed, triggered and successful are distinct states; no scheduler is activated by default.
- Added pinned offline upgrades, known v1.4.0 adoption baseline, private backup journals, collision refusal and rollback preserving new memories/post-upgrade edits. Legacy rollback cannot retain automation capabilities it never had.
- Bounded validation/adoption to managed paths, rejecting links and dependency/runtime leakage. Added strict manifest schema tests, privacy checks and reproducible history-free source packaging.
- Release status: Codex CLI 0.147.0 / Windows 10.0.26100 has earlier real trusted save/new-session recall evidence; this final candidate still requires exact-candidate clean-room review. Claude fixtures use 2.1.273; owner authentication and stable Stop prompt identity must be observed in the real lifecycle. Missing identity is refused, never inferred from reply text.
- Neither a green deterministic suite nor this candidate version authorizes the dual-client release. Actual Claude/cross-client and final release/archive acceptance remain non-optional gates.

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
