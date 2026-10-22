# Tests

`test_human_materials.py` verifies recursive indexing of synthetic nested files,
special-character paths, adds/moves/removals, unread/unparseable status,
duplicate/outside paths, original preservation and symlink rejection.

The tests exercise the file-based lifecycle: first run, changed records, duplicate-safe proposals, source mutation during a run, failure without checkpoint advancement and explicit stale-lock recovery. Run them with `python -m unittest discover -s tests -v` from the project root.

Task continuity tests cover dispatch-only, completed stage without successor, blocker requirements, paused/backlog/future exclusions, freshness, runtime unknown/offline, candidate/reviewer/Manager identity and ordering, malformed input and read-only behavior. External scheduler/worker truth is not simulated as proven live behavior.

Automation contract tests run every case in `fixtures/automation/` (capture, no lesson, failed, partial, interrupted, unsafe, missing runtime, foreign project, paused, duplicate and conflicting delivery) and check event identity, strict schema, support honesty and read-only CLI behavior. They do not exercise a real client.

Bounded scan tests build a synthetic adopted app with dependency, VCS, build and runtime folders, a nested repository, an out-of-scope anchor link, a junction or symlink to a sibling folder and a denied folder, and prove skipped content is never listed, read or copied while broken managed links still fail. The template copy test copies only the managed file list (at most 400 files and 4 MB) and runs only while `PROJECT.md` is still the unfilled template. Every test creates and removes its own temporary directory and starts no background processes.
