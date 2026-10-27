# Developer playbook template

- **GitHub issue before actionable work**: follow [task intake](../../docs/governance/task-intake.md).
  Verify the matching issue/parent and assigned scope before implementation; reuse
  it across messages, commands and stages. Apply its privacy, exception and offline
  pending-sync rules; a local ledger is supplementary evidence.
- Execute only assigned, approved ready work. Check prerequisites, acknowledge actual
  start and deliver the smallest complete candidate with relevant verification.
  Respect owner pauses; report concrete blockers to the Manager without expanding scope.
- Post a stage completion record on that issue and reply to the requester: task
  ID/stage, identity, result, exact candidate SHA/author, checks/limits, and proposed
  next responsible participant/action. The Manager dispatches the successor; an
  author PASS does not establish whole-task acceptance or close the issue.
- Intermediate/feature PRs use `Refs #N` only. Preserve evidence for review fixes;
  do not start another stage or backlog item without assignment/start approval.
