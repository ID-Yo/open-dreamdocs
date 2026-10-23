# Templates

These files are copyable forms, not memory records. Keep them outside `memory/` record directories so retrieval and Dreamer cannot mistake placeholders for active project knowledge. Replace every placeholder before saving a real record.

| Template | Destination |
|---|---|
| [episode](episode.md) | memory/episodes/ |
| [fact](fact.md) | memory/facts/ |
| [skill candidate](skill.md) | memory/procedural/ |
| [contradiction](contradiction.md) | memory/contradictions/ |
| [decision](decision.md) | docs/decisions/ |
| [procedure](procedure.md) | docs/procedures/ |
| [handoff](handoff.md) | docs/status/ |
| [Task snapshot JSON](task.json), [schema](task.schema.json) | Explicit private tracker/runtime adapter; follow [continuity checks](../docs/operations/task-continuity.md) |
| [GitHub labels JSON](github-labels.json) | Explicitly chosen repository; follow the [import procedure](../docs/operations/github-labels.md) |
| [Outcome event schema](outcome-event.schema.json) | Event files written by a client adapter; follow the [automation contract](../docs/operations/automation-contract.md) |
| [Install manifest schema](install-manifest.schema.json) | `memory/automation/install.json`, written by setup; see [first run](../docs/operations/first-run.md) |

Memory templates use JSON frontmatter between `---` delimiters, as described in [SCHEMA.md](../memory/SCHEMA.md). Canonical document templates are drafts until reviewed. A procedure candidate is not an executable agent skill.
