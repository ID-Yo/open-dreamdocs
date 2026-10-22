# Tests

`test_human_materials.py` verifies recursive indexing of synthetic nested files,
special-character paths, adds/moves/removals, unread/unparseable status,
duplicate/outside paths, original preservation and symlink rejection.

The tests exercise the file-based lifecycle: first run, changed records, duplicate-safe proposals, source mutation during a run, failure without checkpoint advancement and explicit stale-lock recovery. Run them with `python -m unittest discover -s tests -v` from the project root.

Task continuity tests cover dispatch-only, completed stage without successor, blocker requirements, paused/backlog/future exclusions, freshness, runtime unknown/offline, candidate/reviewer/Manager identity and ordering, malformed input and read-only behavior. External scheduler/worker truth is not simulated as proven live behavior.

Automation contract tests run every case in `fixtures/automation/` (capture, no lesson, failed, partial, interrupted, unsafe, missing runtime, foreign project, paused, duplicate and conflicting delivery) and check event identity, strict schema, support honesty and read-only CLI behavior. They do not exercise a real client.

Capture tests (`test_memory_capture.py`) cover episode plus receipt with readback and duplicate replay, no-lesson receipts, failed and partial outcomes, crash injection before and after the episode write, full disk and permission denied, conflicting payloads, reordered events, unsafe, oversize and missing-source rejection without copying content, missing binding, README creation, queueing during a Dreamer run, a held writer lock that is never taken over with the 1.5 s limit, and eight real concurrent writer processes. They run the CLI, not a client hook.

Recall tests (`test_memory_recall.py`) cover empty, unavailable and no-match results, episodes captured from Codex and Claude Code events and recalled in a fresh process with exact record and source hashes, exclusion of proposed, superseded, archived, other-project, proposal and template content, source status (ok, changed, missing, superseded, unverified, refused) including a junction escape, contradictions marking disputed facts, the recent-episode limit, the character budget with hostile closing tags, skipped invalid records, read-only behavior and a warm timing bound for 400 records.

Bounded scan tests build a synthetic adopted app with dependency, VCS, build and runtime folders, a nested repository, an out-of-scope anchor link, a junction or symlink to a sibling folder and a denied folder, and prove skipped content is never listed, read or copied while broken managed links still fail. The template copy test copies only the managed file list (at most 400 files and 4 MB) and runs only while `PROJECT.md` is still the unfilled template. Every test creates and removes its own temporary directory and starts no background processes.
