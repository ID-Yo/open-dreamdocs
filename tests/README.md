# Tests

`test_human_materials.py` verifies recursive indexing of synthetic nested files,
special-character paths, adds/moves/removals, unread/unparseable status,
duplicate/outside paths, original preservation and symlink rejection.

The tests exercise the file-based lifecycle: first run, changed records, duplicate-safe proposals, source mutation during a run, failure without checkpoint advancement and explicit stale-lock recovery. Run them with `python -m unittest discover -s tests -v` from the project root.

Task continuity tests cover dispatch-only, completed stage without successor, blocker requirements, paused/backlog/future exclusions, freshness, runtime unknown/offline, candidate/reviewer/Manager identity and ordering, malformed input and read-only behavior. External scheduler/worker truth is not simulated as proven live behavior.
