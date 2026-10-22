---
{"document":"governance-promotion","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Promotion Rules

Dreamer or the agent may propose a change. The area owner reviews active facts, skills, canonical rules and changes to `docs/`.
Automatic capture under the [automation contract](../operations/automation-contract.md) creates only episodes and receipts; it never promotes a record.

## Episode → fact

Before promotion, a claim must have a source, clear scope, sufficient evidence and no conflict with higher authority. Do not promote guesses, temporary details, raw logs or one-off incidents.

## Episodes → skill

By default, these are required:

- a recurring task type;
- at least 3 successful uses;
- stable core steps;
- explicit preconditions and success criteria;
- known failure modes and recovery;
- available and reliable tools.

The owner may deliberately accept a method earlier, but the reason and evidence must be recorded.

## Memory → docs / ADR

Propose a `docs/` change when knowledge becomes canonical: architecture, official workflow, operational rule, product requirement, ownership or a stable constraint. Propose an ADR for a durable decision with significant trade-offs. Dreamer does not automatically accept these changes.

## Archive and duplicate

An exact duplicate or an unambiguously replaced record may be marked with a link to the original/successor. Archiving follows policy, preserves history and respects pinned records; there is no automatic universal expiry period.
