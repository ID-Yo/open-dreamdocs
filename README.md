# open-dreamdocs

A reusable documentation and project-memory template for anyone organizing a
project: community initiatives, research, operations, creative work or software.
Keep agreed project knowledge in `docs/`, and evidence, outcomes and proposed
lessons in `memory/`. Use the folders manually or with an AI assistant.

Version 1.2.0. Licensed under [MIT](LICENSE). The introduction is in English;
most detailed guides and templates are currently in Bulgarian.

## Start with the documents

1. Download this repository or clone it into a new project.
2. Fill in [PROJECT.md](PROJECT.md) with your project's name, purpose and owner.
3. Complete [the platform page](docs/overview/platform.md) and review
   [governance](docs/governance/README.md): who decides what becomes accepted knowledge.
4. Use [the documentation index](docs/00-index.md) to find the relevant pages.
   Keep optional categories only when useful to your project.
5. If you use an AI assistant, adapt [AGENTS.md](AGENTS.md) to its working boundaries.
6. When recording outcomes or lessons, read [the memory guide](memory/README.md),
   [record schema](memory/SCHEMA.md) and [Dreamer policy](memory/DREAMER_POLICY.md).

No programming or running service is needed to use the documents. Unfilled pages
are templates, not project facts. Copy the root template files and `docs/`,
`memory/`, `prompts/`, `scripts/`, `templates/`, `examples/` and `tests/` when
starting a project; retain the MIT license notice.

## What is included

- Thirteen documentation categories, each with a short guide. Overview and
  governance are core; the other categories are optional.
- Governance for authority, memory lifecycle and owner-reviewed promotion.
- Templates and examples for outcomes, facts, procedures and contradictions.
- An optional Python validator and Dreamer lifecycle runner with snapshots,
  checkpoints, reports, proposals and explicit recovery.
- Seventeen tests covering the existing file-based lifecycle and portability.

`docs/` is the canonical home for accepted project knowledge. `memory/` preserves
evidence and proposals. `templates/` and `examples/` are learning materials and
are excluded from active-memory retrieval. Owners review active facts,
procedures and canonical changes; the assistant does not accept its own proposals.
Archiving preserves history and respects pinned records; there is no universal TTL.

## Optional validation and Dreamer

Requires Python 3.11 or later, with no external libraries. From the project root:

```text
python -B scripts/project_memory.py validate
python -B -m unittest discover -s tests -v
```

Dreamer processes inputs since the last successful checkpoint. `begin` creates an
immutable snapshot and a pending `result.json`. An assistant fills in the result;
`finish` validates it and advances the checkpoint only on success. Empty input is
valid. Read [setup and recovery](docs/operations/dreamer-setup.md) before use.

```text
python -B scripts/project_memory.py begin
python -B scripts/project_memory.py finish --run-id <ID>
python -B scripts/project_memory.py abort --run-id <ID>
python -B scripts/project_memory.py recover --run-id <ID> --confirm-stopped --max-age-minutes <N>
```

The global `--root PATH` option precedes the subcommand. Recovery requires
confirmation that execution has stopped and a positive minimum lock age.
See [runner commands](scripts/README.md) and [test scope](tests/README.md).

The template does not activate a scheduler, call an LLM or provide semantic
search. A project may configure its own daily schedule in
[memory/config.json](memory/config.json). Validation checks structure and integrity;
people still verify the truth of claims and the quality of proposals.

## License and provenance

This release packages the project's reusable v1.2 documentation template and
standard-library Python runner under the [MIT license](LICENSE). It starts with
a reviewed source snapshot and fresh public Git history. Archival source
collections, third-party reference documents, private project records, local
agent profiles and runtime state are excluded from this distribution.

[Design notes](DESIGN_NOTES.md) and [the changelog](CHANGELOG.md) describe the
template's existing decisions and evolution.
