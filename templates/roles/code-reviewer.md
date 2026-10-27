# Code Reviewer playbook template

- **GitHub issue before actionable work**: follow [task intake](../../docs/governance/task-intake.md).
  Link the existing task/parent before review; reviewing is a stage of that issue,
  not an issue per comment. Apply privacy, exceptions and offline pending-sync
  rules; private notes and snapshots supplement the issue.
- Review only assigned, approved ready work at the exact candidate SHA and bounded
  acceptance scope. A requested or queued review is not an actual start. Preserve
  owner pauses and report capacity/dependency blockers to the Manager.
- Post a stage completion record on the issue and reply to the requester: task
  ID/stage, reviewer identity, verdict/findings, exact candidate SHA/author,
  checks/limits, and proposed next responsible participant/action. The Manager
  owns successor dispatch and acceptance; approval does not close the issue.
- Intermediate/feature PRs use `Refs #N` only; do not add closing keywords or begin
  unassigned work after reporting the review.
