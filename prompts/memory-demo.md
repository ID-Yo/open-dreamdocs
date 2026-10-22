# Synthetic two-session memory acceptance

Use only in an isolated project extracted from the reviewed candidate, with no private uploads.
Follow [first-run setup](../docs/operations/first-run.md) and the [support matrix](../docs/operations/support-matrix.md).
Authenticate through the chosen client and review/trust its hooks normally. Do not bypass trust,
invoke manual capture/reconcile as proof of automatic saving, or prepopulate demo memory.

In client session A, choose a new random marker and ask:

```text
Create docs/demo-marker.md containing exactly the marker I provide. This is synthetic test data.
Finish with a dreamdocs-outcome block reporting success, a concise summary and one proposed lesson
that includes the marker, with evidence ["file:docs/demo-marker.md"]. Marker: MY_NEW_RANDOM_MARKER
```

After the actual Stop event, observe one persisted receipt and its episode hash/readback. Record
client/session/turn/event IDs privately. A missing identity, skipped hook or failed capture must
remain visible; do not fabricate success. For Claude, a real stable prompt identity on Stop is a
prerequisite still awaiting verification. Setup/fixture passes do not establish it.

Close that session. In a genuinely fresh session B, ask without putting the marker in the prompt:

```text
Use only memory already supplied to this new session. Do not run tools or read project files.
What exact synthetic marker was recorded by the previous session? If absent, say NOT RECALLED.
```

Only a correct marker with no tool/file lookup proves the observed automatic recall path. Repeat
with the other client and both switching directions; a blocked client stays blocked. Compare
receipt/episode bytes and project binding, then run `doctor --smoke` to distinguish isolated engine
readiness from actual client trust/recall. A receipt alone proves neither trust nor fresh recall.

Exercise a failed/queued capture and safe redelivery in a separate throwaway fixture under QA
control. Never inject corruption into real memory or clear a live lock. Use the [executor workflow](../docs/operations/dreamer-execution.md)
for curation and [upgrade guide](../docs/operations/upgrading.md) for a customized old install.
No facts, skills or canonical docs become accepted from this synthetic demo. Remove only the
owned disposable project after recording reviewed evidence; keep user projects and settings intact.
