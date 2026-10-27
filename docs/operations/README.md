# Operations — optional

For an end-to-end explanation of the memory loop, use [How Dreamdocs works](how-it-works.md); for a new machine or project, use the [new computer checklist](new-computer-checklist.md).

For label definitions, combination rules and dry-run-first import, use [GitHub labels](github-labels.md). Select the target and existing status authority explicitly; no mass rollout is implied.

For selective template adoption and the optional companion offer, use [Adopting Dreamdocs](adopting-dreamdocs.md). It covers existing-file collisions and an explicit Yes / No / Skip handoff; it is not an installer.

Describe environments, releases, monitoring, incidents and recovery here. The daily Dreamer is described in [`dreamer-setup.md`](dreamer-setup.md). A repeatable step may have a separate runbook in `procedures/`; do not maintain two versions of one procedure. Do not record production credentials or raw logs. Add the document to the [index](../00-index.md).

For durable task handoffs and observed execution/health metadata, use [Task continuity](task-continuity.md). This read-only audit does not install a scheduler or resume work.

Before actionable work, follow [GitHub issue intake](../governance/task-intake.md).
Local memory, ledgers and snapshots supplement the issue, including during an
explicitly disclosed outage; they do not provide a local-only tracking mode.

For automatic capture and recall in Codex and Claude Code, the shared event, receipt, privacy and exit-code rules are in the [automation contract](automation-contract.md). Nothing in the package is automatic until setup and a tested client adapter exist.

For automatic summaries, tags and sync of the private original-material index, use [Human Materials indexing](human-materials-indexing.md). It is off until the owner chooses `inventory` or `summarize`.
