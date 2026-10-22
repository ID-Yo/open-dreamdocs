# Automation

State for automatic capture, defined in `docs/operations/automation-contract.md`. `receipts/` holds one small committed receipt per saved event. `events/` (exact event files written by an adapter) and `pending/` (captures queued while the writer lock or a Dreamer run was busy) are private local runtime folders: Git ignores them and validation skips them. Neither holds memory records.
