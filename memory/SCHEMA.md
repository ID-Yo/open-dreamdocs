# Record Format

Each real record is Markdown with a **JSON object between two `---` lines**. JSON is a subset of YAML 1.2; it was chosen for precise parsing with standard Python. Arbitrary YAML, comments, trailing commas and duplicate keys are unsupported. Templates are in [templates](../templates/README.md).

## Common fields

`id`, `type`, `status`, `project`, `scope`, `created_at`, `source`. IDs are stable and unique, using lowercase Latin letters, digits, dots, hyphens and underscores. All records in the package belong to one project identity. Timestamps include a timezone. Sources are a nonempty array:

- `id:ep-example` — another real record; the ID must exist, including in the archive.
- `file:docs/architecture/system-overview.md` — an existing file relative to the root.
- `https://...` — an external source; the validator does not open it.
- `ref:issue-123@commit-sha` — an external or non-retrievable identity; a person/agent checks the evidence.

The format guarantees traceability, not truth. Source text and metadata must not contain tokens, personal data or secrets.

| Folder | type | status |
|---|---|---|
| episodes | episodic | active, archived |
| facts | semantic | proposed, active, disputed, superseded, archived |
| procedural | procedural | proposed, active, deprecated, archived |
| contradictions | contradiction | open, resolved, archived |

The archive preserves the original type and terminal status. `pinned: true` prevents an automatic archive proposal.

## Facts and methods

These require `owner`. When `active`, they require `last_verified` and `accepted_by` with real acceptance evidence; Dreamer cannot activate them itself. A proposal may have `last_verified: null`. `review_after` is a YYYY-MM-DD date or null, chosen for the topic.

`supersedes` and `superseded_by` contain real IDs without a prefix; `superseded` requires a successor. A method has a positive `version` and nonnegative `success_count` and `failure_count`. A success count is not automatic authorization to execute or accept it.

## Retrieval

Read only relevant records. Archives, superseded/deprecated records, templates, examples and Dreamer work/reports/proposals are not active facts. A proposal is for review, never an operational instruction. The template code validates and selects Dreamer input; it does not provide semantic search or embeddings.

## Task evidence is separate

Operational tasks are not new memory record types. The optional [task snapshot contract](../docs/operations/task-continuity.md) uses a separate JSON schema and read-only checker; memory validation and configured scheduling do not prove worker execution or runtime health.

## Automatic capture

Automatically captured work becomes an ordinary `episodic` record named `auto-<event_id>.md` with a receipt, as defined in the [automation contract](../docs/operations/automation-contract.md). Events carry no record status, owner or acceptance fields, so capture cannot create active facts or methods. The project binding lives in `memory/automation.json`; `config.json` stays version 1.
