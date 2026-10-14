---
{"document":"governance-authority","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Authority Model

This is the single canonical hierarchy of sources. User authorization defines the scope of work; it does not prove that a remembered claim is true.

## Default hierarchy

1. Current live system or current code
2. Explicit current configuration
3. Accepted ADR
4. Current documentation in `docs/`
5. Active semantic memory record
6. Episodic memory record
7. Agent inference

## Runtime truth and intended design

For current behavior, runtime evidence may outrank documentation. For intended architecture, an accepted ADR may outrank an incidental implementation defect. When they disagree, record the difference and identify the owner who must decide.

## Conflict with memory

Check against the higher-authority source. If an accepted replacement exists, the owner marks the old record as `superseded`. If evidence is unclear, propose `disputed` and create a `contradiction` for review. Do not maintain two active versions of one claim without a scope and reason.

## Domain overrides

| Area | Highest source | Note |
|---|---|---|
| ... | ... | ... |
