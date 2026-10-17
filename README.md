# open-dreamdocs

A reusable documentation and project-memory template for anyone organizing a
project: community initiatives, research, operations, creative work or software.
Keep agreed project knowledge in `docs/`, and evidence, outcomes and proposed
lessons in `memory/`. Use the folders manually or with an AI assistant.

Version 1.4.0. Licensed under [MIT](LICENSE). All guides, templates, examples and prompts are in English.

## Start with the documents

1. Download a clean release. For an existing project, follow the [adoption and optional companion guide](docs/operations/adopting-dreamdocs.md) before copying; merge existing rules safely.
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
`memory/`, `prompts/`, `scripts/`, `templates/`, `examples/`, `tests/` and the clean
`human-materials/` scaffolding when
starting a project; retain the MIT license notice.

During adoption, optionally consider [Codex Bot Mode](https://github.com/ID-Yo/codex-bot-mode)
for persistent approved roles and coordination. Choose **Yes / No / Skip** using
the [companion offer](docs/operations/adopting-dreamdocs.md); Dreamdocs works
independently and never installs a companion silently.

## What is included

- Fourteen documentation categories, each with a README and scoped AGENTS guidance. Overview and
  governance are core; the other categories are optional.
- Governance for authority, memory lifecycle and owner-reviewed promotion.
- Templates and examples for outcomes, facts, procedures and contradictions.
- An optional Python validator and Dreamer lifecycle runner with snapshots,
  checkpoints, reports, proposals and explicit recovery.
- Tests covering the file-based lifecycle, portability and recursive material indexing.
- A portable [GitHub labels template and import guide](docs/operations/github-labels.md), applied only to an explicitly chosen repository and workflow.
- Independent [Marketing fields](docs/marketing/README.md) and an indexed home for
  [original human materials](human-materials/README.md).

`docs/` is the canonical home for accepted project knowledge. `memory/` preserves
evidence and proposals. `templates/` and `examples/` are learning materials and
are excluded from active-memory retrieval. Owners review active facts,
procedures and canonical changes; the assistant does not accept its own proposals.
Archiving preserves history and respects pinned records; there is no universal TTL.

For a public copy, include only the empty `human-materials/README.md` template and
its `.gitignore`; never copy uploaded originals or a populated index by default.
Review the exact staged inventory, including filenames/descriptions in the index.
Private project copies also need explicit handling of their originals; bulk copying
a used checkout is not a safe template-export procedure. Follow the
[material privacy and reconciliation procedure](human-materials/README.md).

## Optional validation and Dreamer

Requires Python 3.11 or later, with no external libraries. From the project root:

```text
python -B scripts/project_memory.py validate
python -B scripts/human_materials.py --root .
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

This release packages the project's reusable documentation template and
standard-library Python runner under the [MIT license](LICENSE). It starts with
a reviewed source snapshot and fresh public Git history. Archival source
collections, third-party reference documents, private project records, local
agent profiles and runtime state are excluded from this distribution.

[Design notes](DESIGN_NOTES.md) and [the changelog](CHANGELOG.md) describe the
template's existing decisions and evolution.

For optional machine-readable task handoff checks, see [Task continuity](docs/operations/task-continuity.md). The checker audits reported evidence; it does not run a scheduler or ensure host availability.
