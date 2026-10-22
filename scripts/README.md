# Validation and Dreamer Lifecycle

[automation_contract.py](automation_contract.py) checks one automation event against the
[v1 contract](../docs/operations/automation-contract.md): `python -B scripts/automation_contract.py --root . --event FILE`.
It reads `memory/automation.json` and an existing receipt when present, prints the decision and planned
identifiers, and writes nothing. Exit codes: 0 allowed, 1 pending or non-success outcome, 2 invalid,
3 rejected, 4 degraded (not installed, manual only), 5 conflict.

[dreamdocs.py](dreamdocs.py) persists events through [memory_capture.py](memory_capture.py):

```text
python -B scripts/dreamdocs.py memory capture --event FILE [--budget-ms 1000]
python -B scripts/dreamdocs.py memory reconcile
```

`capture` checks the event, then under the writer lock shared with Dreamer writes the episode, reads it back, writes the receipt and reads it back; only then is `saved` true. Replaying the same bytes returns `duplicate`. If the lock is busy past the budget or a Dreamer run is active, the checked capture is queued in `memory/automation/pending/` (exit 1, not saved) and published by the next capture or by `reconcile`. Missing `file:` sources are refused before queueing. A queued entry that is refused (for example an unknown `id:` source) or conflicts at drain time stays in the queue and is listed under `unpublished` in the capture and reconcile output; `reconcile` exits 5 when any entry conflicts, 2 when any is refused and 0 only when nothing is left unpublished. Write failures return `error` (exit 2) and never report saved. Refused events (`reject`, `invalid`) write nothing; the exit code and findings report them without echoing event content. Call `capture` at `Stop`, where the event is saved durably. `--budget-ms` bounds only the wait for the writer lock; once the lock is held, the time grows with the number of memory records and queued entries (a new capture took 0.38 s through the CLI with 170 records on the reference Windows host). A replay whose receipt already exists is answered from the receipt before the lock is touched (0.27-0.29 s through the CLI with 170 records and a live lock); this is the `SessionEnd` case after a save at `Stop`. If a client kills the hook while it holds the lock, the lock stays and later captures queue until an operator confirms that the recorded owner has stopped and removes it; the doctor (#22) is to report such locks. No client adapter calls these commands yet.

```text
python -B scripts/dreamdocs.py memory recall [--project ID] [--query TEXT] [--max-chars 4000] [--episodes 5]
```

`recall` is read-only. It prints JSON with `status` (`ok`, `no_match`, `empty` or `unavailable`), the selected items with record and source hashes and source status, findings for skipped invalid records, and `context`: a block of at most `--max-chars` characters framed as untrusted data, for a `SessionStart` or `UserPromptSubmit` hook to inject. The project comes from `--project` or `memory/automation.json`. Exit 0 for ok, no match and empty; exit 4 when the store or project scope is unavailable. Adapters must treat a nonzero exit as non-blocking. Measured on Windows with Python 3.13: a CLI call takes about 0.3 s for 50 records and 0.5 s for 400 once files have been opened before; the first read of freshly written files can take over 1 s because of antivirus scanning.

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

Scanning is bounded so the validator works inside an adopted application. Managed files are root-level Markdown, `LICENSE`, `.gitignore`, the `human-materials` index files and the folders `docs`, `memory`, `templates`, `examples`, `prompts`, `scripts` and `tests`. Everything else, including the application's own `build`, `dist` or `node_modules` at the root, is never listed. Inside managed folders, tool folders (`.git`, `node_modules`, `.venv`, `__pycache__` and similar), Python environments of any name (a folder containing `pyvenv.cfg`), the runtime folders `memory/dreamer/work`, `memory/automation/events` and `memory/automation/pending` and nested repositories are skipped before they are listed; generic names such as `build` or `work` are scanned normally. Inside memory record folders nothing is skipped silently: such a folder stops validation as unexpected. A symlink or junction inside a managed folder stops validation with `linked path`, an unreadable managed folder stops it with `permission denied`, and neither is treated as an empty folder. Links into skipped areas are checked for existence only; their contents and anchors are never read. Root-level Markdown counts as managed, so in an adopted app a broken link in the app's own README or CONTRIBUTING also fails validation.
