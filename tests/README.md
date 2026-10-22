# Tests

Release-package tests audit synthetic Git snapshot/history contamination, credential patterns,
empty material scaffolding, dirty-source refusal, non-overwrite and byte-identical ZIP/inventory/
updater manifests. They do not replace real client download-to-memory or publication acceptance.
Run the entire suite in both reviewed Git source and the generated ZIP. The history-free ZIP
explicitly skips the single v1.4.0 archive test when its external historical Git fixture is absent;
the Git-source suite must run that test before release. Record artifact skip counts honestly.

Dreamer executor tests cover explicit operator/command identity, real process/CLI execution,
budgets/timeout and owned descendant cleanup, shared locks, failed/partial/stale results and
checkpoint interruption/readback. Scheduler tests simulate opt-in install/duplicates/disable/remove,
pause/denial/timezone changes, bounded catch-up and trigger+executor+checkpoint correlation. These
simulations do not prove actual Windows scheduled-trigger acceptance or semantic review.

Documentation refresh tests cover accepted candidate/source binding, independent acceptance,
stale/rolled-back evidence, owner target limits, private immutable sidecars, routing/status/history,
Dreamer committed-checkpoint linkage, concurrent edits and material add/move/remove/partial/failed
coverage without reading originals. Public-export checks include populated indexes and private prose
outside the table. These tests verify deterministic proposal transport, not semantic truth/promotion.

`test_human_materials.py` verifies recursive indexing of synthetic nested files,
special-character paths, adds/moves/removals, unread/unparseable status,
duplicate/outside paths, original preservation and symlink rejection.

The tests exercise the file-based lifecycle: first run, changed records, duplicate-safe proposals, source mutation during a run, failure without checkpoint advancement and explicit stale-lock recovery. Run them with `python -m unittest discover -s tests -v` from the project root.

Task continuity tests cover dispatch-only, completed stage without successor, blocker requirements, paused/backlog/future exclusions, freshness, runtime unknown/offline, candidate/reviewer/Manager identity and ordering, malformed input and read-only behavior. External scheduler/worker truth is not simulated as proven live behavior.

Automation contract tests run every case in `fixtures/automation/` (capture, no lesson, failed, partial, interrupted, unsafe, missing runtime, foreign project, paused, duplicate and conflicting delivery) and check event identity, strict schema, support honesty and read-only CLI behavior. They do not exercise a real client.

Capture tests (`test_memory_capture.py`) cover episode plus receipt with readback and duplicate replay, no-lesson receipts, failed and partial outcomes, crash injection before and after the episode write, full disk and permission denied, conflicting payloads, reordered events, unsafe, oversize and missing-source rejection without copying content, missing binding, README creation, queueing during a Dreamer run, a held writer lock that is never taken over with the 1.5 s limit, and eight real concurrent writer processes. They run the CLI, not a client hook.

Recall tests (`test_memory_recall.py`) cover empty, unavailable and no-match results, episodes captured from Codex and Claude Code events and recalled in a fresh process with exact record and source hashes, exclusion of proposed, superseded, archived, other-project, proposal and template content, source status (ok, changed, missing, superseded, unverified, refused) including a junction escape, contradictions marking disputed facts, the recent-episode limit, the character budget with hostile closing tags, skipped invalid records, read-only behavior and a warm timing bound for 400 records.

Bounded scan tests build a synthetic adopted app with dependency, VCS, build and runtime folders, a nested repository, an out-of-scope anchor link, a junction or symlink to a sibling folder and a denied folder, and prove skipped content is never listed, read or copied while broken managed links still fail. The template copy test copies only the managed file list (at most 400 files and 4 MB) and runs only while `PROJECT.md` is still the unfilled template. Every test creates and removes its own temporary directory and starts no background processes.

Adapter and setup tests (`test_codex_adapter.py`, `test_setup.py`) run the Codex hook as a real subprocess with recorded Codex 0.147.0 payloads and run setup in a project path with spaces and non-ASCII characters: dry run, idempotent apply, preserved user hooks and AGENTS.md rules through setup and uninstall, conflicts, a missing client, memory kept after uninstall, and the generated hook command run by the system shell. They do not start Codex.
