# Verifier playbook template

- **GitHub issue before actionable work**: follow [task intake](../../docs/governance/task-intake.md).
  Reuse the assigned task/parent before QA. Tests and acceptance stages share that
  issue rather than creating an issue per command. Apply privacy, exceptions and
  offline pending-sync rules; local evidence does not replace the issue.
- Verify only assigned, approved ready work against the exact candidate SHA and
  acceptance criteria. Record actual start; distinguish verified results, limits
  and device/client checks still needed. Preserve pauses and report blockers to Manager.
- Post a stage completion record on the issue and reply to the requester: task
  ID/stage, verifier identity, result, exact candidate SHA/author, checks/limits,
  and proposed next responsible participant/action. The Manager dispatches the
  successor and accepts the whole task; a QA PASS alone does not close it.
- Intermediate/feature PRs use `Refs #N` only. Do not resume unrelated or unapproved
  work after delivering this stage.
