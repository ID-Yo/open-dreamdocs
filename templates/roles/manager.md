# Manager playbook template

- **GitHub issue before actionable work**: follow [task intake](../../docs/governance/task-intake.md).
  Reuse a matching existing/parent issue before dispatch; create a child only for
  independent ownership or acceptance. Enforce privacy, exceptions and offline
  pending-sync disclosure; local evidence is supplementary.
- Dispatch only approved ready work with bounded scope, acceptance, executor and
  next action. Backlog, future and owner-paused work stay inactive; priority does
  not approve execution. Verify actual start, not just dispatch.
- After each stage, inspect the stage completion record on the issue and reconcile
  exact candidate/evidence. Dispatch and verify the next responsible participant's
  actual start, or record blocker reason, unblock owner, resume condition and next
  check. Independent review/QA and Manager acceptance precede completion/closure.
- Post your own stage completion record and reply to the requester: task ID/stage,
  identity, result, exact candidate SHA/author where applicable, checks/limits,
  next responsible participant/action. Intermediate/feature PRs use `Refs #N` only.
