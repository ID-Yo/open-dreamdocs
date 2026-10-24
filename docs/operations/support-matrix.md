---
{"document":"support-matrix","status":"draft","owner":"<project-owner>","last_reviewed":"2026-10-22"}
---

# Candidate support and evidence

Package: **1.5.0-rc.2**. This is a candidate, not a released dual-client support claim.
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
| Windows scheduler | Simulated tests, real read-only COM query and TASK_VALIDATE_ONLY XML validation | No installed-task/real-trigger/offline/restart acceptance; separate explicit owner opt-in |

Executor transport and schedule-preview code acceptance is narrower than complete #21 runtime
acceptance. Real installed-trigger/offline/restart/uninstall evidence remains unverified. Likewise,
data-preservation upgrade tests do not prove automatic client lifecycle behavior after upgrade or
rollback. These limits remain visible while RC packaging is reviewed.

Historical candidate hashes identify prior evidence; they do not attest to later code changes.
Private transcripts, owner config, raw reports and machine paths are not shipped as public proof.
The Manager/QA must bind final acceptance to the exact package/manifest/archive hashes. The engine's
compatibility table stays conservative until those runtime observations are accepted.

## Official hook references rechecked 2026-10-22

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
