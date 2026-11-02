---
{"document":"support-matrix","status":"draft","owner":"<project-owner>","last_reviewed":"2026-11-02"}
---

# Release support and evidence

Package: **1.6.0 stable** for the reusable documentation template and Python tools.
This is not a released dual-client integration support claim.
An installed file, fixture pass, capture receipt, trusted hook and fresh-session recall prove
different things. The [release checklist](release.md) requires exact-candidate independent evidence.

| Surface | Evidence available on 2026-10-22 | Candidate gate |
|---|---|---|
| Python engine | Standard-library Python 3.11+ contract; tests run on Python 3.13.12, Windows 10.0.26100 | Full candidate suite and clean-package test required |
| Codex CLI 0.147.0 | Earlier trusted project-hook save, automatic redelivery and fresh-session recall passed on Windows; tested source d98657b1df611b53a4dd344b85036175d01ae7d4 | Final download/candidate repeat pending; Desktop/other OS not established |
| Claude Code 2.1.273 fixture baseline | Recorded payload fixtures/setup only; command+args exec form is documented, authenticated lifecycle still unverified | Owner sign-in, real Stop identity/save/new-session recall required; no prompt_id means refusal |
| Switching clients | Shared project binding/record format tested with fixtures | Real Codex→Claude and Claude→Codex new-session recall pending |
| Upgrade/rollback | v1.4.0 revision 26c7aff57be6ffb4ccd6287c979e3782a0a19b2a adoption and data-preserving automation-version rollback passed independent QA at d7f2be77c790aa8324f15ad076c651a142b8cc96 | Final package pin/inventory plus real automatic probes after upgrade AND rollback required |
| Dreamer operator | Actual isolated synthetic operator review, proposed contradiction and checkpoint readback observed | Does not establish production semantics or automatic scheduling |
| Windows scheduler | Simulated tests, real COM query, installed tasks and successful scheduled execution/readback in local candidate rollouts | Exact-package client acceptance and offline/restart behavior remain unverified; separate explicit owner opt-in |

Executor transport and local installed-trigger observations are narrower than complete #21 runtime
acceptance. Offline/restart/uninstall acceptance remains unverified. Likewise,
data-preservation upgrade tests do not prove automatic client lifecycle behavior after upgrade or
rollback. These limits remain visible while RC packaging is reviewed.

Historical candidate hashes identify prior evidence; they do not attest to later code changes.
Private transcripts, owner config, raw reports and machine paths are not shipped as public proof.
The Manager/QA must bind final acceptance to the exact package/manifest/archive hashes. The engine's
compatibility table stays conservative until those runtime observations are accepted.

## Operational observations and remaining limits

Local Windows rollout of the 1.6.0 candidates exercised capture/status generation and explicit
Dreamer execution across 20 project roots. Installed Windows tasks and matching successful
execution/report/checkpoint readbacks were observed. Later scheduled runs also exposed model-capacity
failures; those runs did not advance checkpoints. These observations do not prove unattended model
availability, reboot/offline recovery or exact-final-artifact client acceptance. The shipped runner
requires a separately selected executor; private local model wrappers and schedules are not included.

The rc.7 tagged-outcome fix was exercised through an installed Codex Stop adapter, with episode
and generated-status readback plus duplicate replay checks. Explicit adapter invocation is not
independent evidence that every desktop turn fires its hook. The compatibility table remains
conservative, and Claude Code and client switching remain experimental.

Generated activity/status pages repeat saved agent reports. Topic pages still require task-level
updates and review. Docs debt is a heuristic: any topic-doc edit or an `updated` declaration currently
clears accumulated debt, and generated operational JSON outside excluded output paths may count as
code. Zero debt is not proof of documentation coverage. These known limits are not silently fixed
or claimed resolved by this release.

## Official hook references last rechecked 2026-10-22

- [Codex hook reference](https://learn.chatgpt.com/docs/hooks): project trust, review of changed hooks,
  lifecycle event/payload and context output rules. Dreamdocs uses SessionStart, UserPromptSubmit,
  Stop and SessionEnd; final outcomes are saved at Stop rather than depending on session shutdown.
- [Claude Code hook reference](https://code.claude.com/docs/en/hooks): event/exec-form payload contract,
  project-local configuration and StopFailure. It documents prompt_id among common fields,
  absent before first user input. Exec form has no stated version minimum in that paragraph;
  adjacent minimum-version notes apply to other fields. Documentation does not replace
  observing that identity on a real Stop. No identity is inferred from identical reply text.

Recheck these references and actual installed-client versions at release. Model/account selection
and client authentication stay user choices. The package does not purchase credits, log in,
change models, bypass trust, install companion agents or enable a scheduler automatically.

The `doctor` compatibility label is the conservative package support-table state, not a dynamic
version rejection. Codex CLI 0.147.0 is the recorded observed Windows client; `unsupported`
does not mean the executable version was rejected. Real hooks/trust/save/recall acceptance
and supported release status are separate. RC2 does not widen the support table.
