# Dreamer Runtime

`work/` contains the snapshot and pending result; `lock.json` identifies the current run; `command.lock` serializes CLI operations. `state.json` is the last successfully completed checkpoint. These files are local and ignored by Git.

[reports](reports/README.md) contains reports, and [proposals](proposals/README.md) contains candidates for review. None of these files is automatically included in active memory. Do not place a fictitious successful checkpoint in the template.

When starting a new project, copy only the clean package. When copying a used checkout, exclude work/lock/state and old runtime reports/proposals. Follow the [policy](../DREAMER_POLICY.md) for recovery and writer coordination.
