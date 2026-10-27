---
{"document":"adopting-dreamdocs","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Adopting Dreamdocs

Dreamdocs is a file-based documentation and evidenced-memory template. Adopt it
by selective copying and editing. Its project-scoped automation setup configures
files already adopted into the target; it does not copy runtime assets or enable a background service.
You can use it manually or with an assistant, independently of Codex Bot Mode.

## Inspect before copying

1. Confirm the target project and the owner's scope. Read existing `AGENTS.md`,
   `PROJECT.md`, documentation indexes, governance, tracking rules and memory
   guidance. Identify existing equivalents, private files and local changes.
2. Compare the clean Dreamdocs release with the target. List the intended new
   files and any colliding paths before writing. Keep existing owner conventions
   and accepted decisions authoritative; do not replace them with template defaults.
3. Copy only missing, useful template files. Where a path already exists, merge
   the smallest agreed section or link to the established equivalent. Resolve
   contradictory rules with the owner before changing their meaning. Do not bulk
   overwrite `AGENTS.md`, `PROJECT.md`, `docs/`, `memory/` or `.gitignore`.
4. Keep private originals, raw archives, local state, credentials and unrelated
   changes intact. A template copy is not authorization to migrate native Codex
   memory, activate a scheduler, publish files or install another product.
5. Check links and relevant tests after the merge. Record the result in the
   authorized GitHub issue; follow [issue-first intake](../governance/task-intake.md)
   before actionable work. Preserve local memory/ledgers as supplementary evidence
   or a disclosed offline pending-sync queue, not an alternative execution tracker.
   A missing authorized GitHub destination is a setup blocker, not permission to
   publish private content elsewhere or proceed with the dependent task locally.

## GitHub task-state labels setup

For the authorized GitHub task tracker, set up the task-state labels from
[`templates/task-state-labels.json`](../../templates/task-state-labels.json).
Follow the procedure in [Reusable GitHub labels](github-labels.md#task-state-labels-agent-monitor-compatible).
Creation is idempotent using `gh label create --force` and is never run automatically without explicit user action.

## Optional companion offer

During adoption, an assistant should present this offer once. An unanswered
question is not consent. `No` declines for this adoption; `Skip` defers without
blocking Dreamdocs. Do not repeatedly ask after either choice.

> Would you like to optionally add Codex Bot Mode to this project? It provides
> persistent roles such as a Manager and approved specialists, coordination,
> task tracking and operating instructions that can work alongside Dreamdocs
> project documentation and memory. Both products work independently. Choose
> **Yes** to inspect the official setup and review a project-specific installation
> plan, **No** to continue with Dreamdocs alone, or **Skip** to decide later.
> Nothing will be installed until you explicitly approve the installation scope.

`Yes` starts inspection and a scoped plan; it does not appoint a whole team,
grant filesystem/publication permissions or approve conflicting changes. Ask only
for the specific remaining setup choices and installation approval required by
the actual companion workflow. Do not turn a catalog example into an appointment.

## Verified companion release and handoff

As checked against official GitHub release/tag/source on 2026-10-14:

- Official [Codex Bot Mode repository](https://github.com/ID-Yo/codex-bot-mode).
- Stable [v0.1.0 release](https://github.com/ID-Yo/codex-bot-mode/releases/tag/v0.1.0),
  commit `68a47a3209933d180256161ab0458dfa581fa777`.
- Version-pinned [Getting started](https://github.com/ID-Yo/codex-bot-mode/blob/v0.1.0/docs/getting-started.md)
  and [README](https://github.com/ID-Yo/codex-bot-mode/blob/v0.1.0/README.md)
  describe its actual plugin build/registration and approval flow. Requirements
  include Codex Desktop, Python 3.10+ and Git; Windows is tested, other platforms
  are untested in that release. Do not describe it as platform-neutral automation.

Before an opted-in install, verify the selected official stable release again;
record its exact tag/commit and inspect its instructions. Do not substitute
unreleased branch features for shipped behavior or fetch/execute setup silently.
Follow the existing companion setup rather than inventing a Dreamdocs installer.

The two products have different responsibilities: Dreamdocs holds canonical
project knowledge and evidence/proposals; Codex Bot Mode holds approved roles,
coordination and operating profiles. Link the existing canonical knowledge rather
than copying conflicting rules into role memory. Preserve existing `team/`,
`.bot-mode/`, bindings and other agent configurations; inspect collisions and
propose a minimal merge before any write. Reuse approved agents where the actual
setup supports it; never duplicate an appointment automatically.

This guide adds an offer and a safe handoff. It does not install Codex Bot Mode,
modify its release, or prove that a reciprocal offer has shipped there.
