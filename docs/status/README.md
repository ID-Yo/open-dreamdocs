# Status — optional

Store temporary current state here: open questions, blockers and next steps. Each entry identifies its verification date and owner; old status is not evidence of current state. On completion, move durable decisions to the appropriate canonical folder. Add current pages to the [index](../00-index.md).

Automatic status updates and the local docs-debt signal follow [ADR-0001](../decisions/ADR-0001-automatic-documentation.md).
Debt inspects individual untracked files, so adding a source directory counts. Generated artifacts under
`output/` are excluded; previously recorded debt is filtered by the same rules when read.
