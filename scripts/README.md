# Validation and Dreamer Lifecycle

[automation_contract.py](automation_contract.py) checks one automation event against the
[v1 contract](../docs/operations/automation-contract.md): `python -B scripts/automation_contract.py --root . --event FILE`.
It reads `memory/automation.json` and an existing receipt when present, prints the decision and planned
identifiers, and writes nothing. Exit codes: 0 allowed, 1 pending or non-success outcome, 2 invalid,
3 rejected, 4 degraded (not installed, manual only), 5 conflict.

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

The validator checks known memory categories, local Markdown links in managed files, valid source IDs/file references, duplicate IDs, statuses, structured frontmatter, dates and checkpoint. The reviewing agent/person checks HTTPS and ref: sources. The CLI does not execute input text. Adding a new memory type requires code and test changes.

Scanning is bounded so the validator works inside an adopted application. Managed files are root-level Markdown, `LICENSE`, `.gitignore`, the `human-materials` index files and the folders `docs`, `memory`, `templates`, `examples`, `prompts`, `scripts` and `tests`. Everything else, including the application's own `build`, `dist` or `node_modules` at the root, is never listed. Inside managed folders, tool folders (`.git`, `node_modules`, `.venv`, `__pycache__` and similar), the runtime folder `memory/dreamer/work` and nested repositories are skipped before they are listed; generic names such as `build` or `work` are scanned normally. Inside memory record folders nothing is skipped silently: such a folder stops validation as unexpected. A symlink or junction inside a managed folder stops validation with `linked path`, an unreadable managed folder stops it with `permission denied`, and neither is treated as an empty folder. Links into skipped areas are checked for existence only; their contents and anchors are never read. Root-level Markdown counts as managed, so in an adopted app a broken link in the app's own README or CONTRIBUTING also fails validation.
