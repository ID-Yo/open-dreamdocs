# Tests

`test_human_materials.py` verifies recursive indexing of synthetic nested files,
special-character paths, adds/moves/removals, unread/unparseable status,
duplicate/outside paths, original preservation and symlink rejection.

The tests exercise the file-based lifecycle: first run, changed records, duplicate-safe proposals, source mutation during a run, failure without checkpoint advancement and explicit stale-lock recovery. Run them with `python -m unittest discover -s tests -v` from the project root.
