<!-- dreamdocs:automation:start -->
## Project memory outcome block

When you finish a meaningful task in this project (a change, finding or decision that matters later), end your final message with one fenced block:

```dreamdocs-outcome
{"status": "success", "summary": "One or two sentences on what changed and why.", "lessons": ["A reusable lesson, only if there is one."], "evidence": ["file:docs/changed-page.md"], "task": {"id": "ISSUE-12", "status": "done"}}
```

- `status` is `success`, `partial`, `failed` or `no_lesson`. Use `lessons: []` when nothing is worth remembering; at most 10 lessons of 600 characters.
- `evidence` uses `file:` (an existing project file), `id:`, `https://` or `ref:` references. `task` is optional and is only your report, never acceptance.
- Never put secrets, personal data or raw logs in the block. Skip it for trivial replies.
- The hook saves the block as an unreviewed episode; it never becomes an accepted fact without review.
<!-- dreamdocs:automation:end -->
