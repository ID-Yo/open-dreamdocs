# Validation and Dreamer Lifecycle

[task_continuity.py](task_continuity.py) audits an explicitly named private task
snapshot: `python -B scripts/task_continuity.py --file PATH`. Exit 0 means consistent
reported metadata; exit 1 means findings or unreadable input. It never dispatches,
schedules or independently verifies external references. See [contract and limits](../docs/operations/task-continuity.md).

[human_materials.py](human_materials.py) is a separate read-only index checker.
Run `python -B scripts/human_materials.py --root .` after reconciling the
[material index](../human-materials/README.md). It scans names recursively and
checks linked rows, metadata shape and coverage without opening originals.
Exit 0 means the index matches; exit 1 reports discrepancies or unreadable index.
Descriptions, review truth and extraction quality remain the agent's responsibility.

Requires Python 3.11+ with no external libraries. [project_memory.py](project_memory.py) validates records/config/links and manages the lock, snapshot, reports/proposals and checkpoint. It does not call an LLM, install a scheduler or prove factual accuracy.

```text
python scripts/project_memory.py validate
python scripts/project_memory.py begin
python scripts/project_memory.py finish --run-id ID
python scripts/project_memory.py abort --run-id ID
python scripts/project_memory.py recover --run-id ID --max-age-minutes 1440 --confirm-stopped
python scripts/project_memory.py --root PATH validate
python -B -m unittest discover -s tests -v
```

The global --root option precedes the command. begin creates a pending result; the agent fills it in according to the [policy](../memory/DREAMER_POLICY.md). Exit codes: 0 success, 1 partial/failed, 2 invalid input/runtime error. validate permits null scheduler fields in an unconfigured template and reports scheduler_configured=false.

The validator checks known memory categories, all local Markdown links outside work, valid source IDs/file references, duplicate IDs, statuses, structured frontmatter, dates and checkpoint. The reviewing agent/person checks HTTPS and ref: sources. The CLI does not execute input text. Adding a new memory type requires code and test changes.
