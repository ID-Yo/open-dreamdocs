---
{"document":"governance-lifecycle","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Memory Lifecycle

```text
observation -> episode -> fact/skill candidate -> verification
-> active fact/skill -> review -> superseded / deprecated / archived
```

## Capture

Completed meaningful work may produce one concise episode with outcome and evidence.

## Extract and validate

Extract only knowledge likely to be useful again. Check the candidate against code, configuration, ADRs, `docs/` and owner feedback.

## Promote

Promotion changes status and follows the review described in [promotion rules](promotion-rules.md). A candidate does not become active merely because it is old or frequently retrieved.

## Retrieve and review

Load only records related to the current task. During review, check evidence, scope, contradictions, broken links and implementation changes. There is no universal TTL: project policy determines when a record is reviewed, pinned or archived.

## Supersede and archive

Prefer traceable replacement to silent overwriting. Archive only with a reason, date and link to the successor when one exists; respect `pin` and project rules. Archiving stops normal retrieval but preserves history.
