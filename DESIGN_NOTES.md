# Design Notes

v1.2 was created as a small, portable file-based template. It assumes no particular provider, running scheduler or automated semantic judgment.

## Main decisions

1. `docs/` is the only canonical home for project documentation. The former `wiki/` split has been removed.
2. All thirteen topic folders exist from day one. Each has a short README; only overview and governance are core, and the others are optional.
3. `PROJECT.md` is a short entry point linking to `docs/overview/platform.md`, avoiding two versions of the platform description.
4. Governance documents are the single home for authority, lifecycle and promotion rules. Other pages link to them.
5. Retrieval is selective: the agent reads only relevant canonical pages and records. `templates/` and `examples/` are not active records.
6. The agent proposes facts, skills and changes; the owner reviews their activation and changes to canonical rules. Archiving follows project policy and respects pinned records, with no universal TTL.
7. The daily Dreamer starts from the last successful checkpoint, uses an immutable snapshot and editable `result.json`, and writes the checkpoint and outputs only after successful validation.
8. The snapshot includes a complete manifest and input hashes. Documents are read as needed, and generated reports and proposals do not feed back into the input.
9. `memory/config.json` is a JSON settings file. The runner and tests are a separate integration and do not turn the template into an active service.

This version provides a contract for structure and operations. It does not guarantee factual accuracy, the quality of model proposals or successful scheduler setup in every project.
