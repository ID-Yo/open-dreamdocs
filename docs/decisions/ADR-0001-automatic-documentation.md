---
{"document":"adr-0001","status":"accepted","owner":"<project-owner>","decided_at":"2026-10-28"}
---

# ADR-0001: Automatic documentation in three tiers

## Context

Captured outcomes reached memory, but the project documentation did not change. The proposal-only
[documentation refresh](../operations/documentation-refresh.md) needs a manual policy, an accepted
task snapshot and source hashes. In practice no project configured it, so status pages stayed weeks
old while many outcomes were saved every day.

## Decision

Documentation is written in three tiers:

| Tier | Pages | Written by | Review |
|---|---|---|---|
| A. Status | `docs/status/activity-log.md` and the generated block in `docs/status/current-state.md` | Dreamdocs, automatically, from every saved outcome | None; the content is marked generated and is the agent's own report |
| B. Topic pages | `docs/<category>/<topic>.md` | The agent, in the same change or PR as the code | With the code, in normal review; a change without docs leaves visible docs debt |
| C. Governance | `AGENTS.md`, `docs/governance/`, decisions, active facts and skills | Proposals only | The owner, unchanged |

Tier A is deterministic: no model, network or transcript. It writes only the activity log and the
text between the `dreamdocs:recent` markers. Owner text outside the markers stays byte for byte.
A project can switch tier A off with `{"automatic_status": false}` in `.dreamdocs/documentation.json`.

## Consequences

- Status documentation is current after every saved outcome, including outcomes saved later from a queue.
- Generated lines repeat agent reports. They are not verified facts and do not promote memory.
- Docs debt is a local signal in `.dreamdocs/docs-state.json`, shown at session start and by doctor.
  It never blocks the agent.
- The proposal-only refresh helper remains for tier C changes.

## Alternatives considered

- Keep proposal-only refresh: rejected, since it was never used and the docs went stale.
- Let a model rewrite topic pages automatically: rejected for tier A; tier B keeps a reviewer.

