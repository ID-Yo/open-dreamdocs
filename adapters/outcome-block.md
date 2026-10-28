<!-- dreamdocs:automation:start -->
## Project memory outcome block

When you finish a meaningful task in this project (a change, finding or decision that matters later), end your final message with one fenced block:

```dreamdocs-outcome
{"status": "success", "summary": "One or two sentences on what changed and why.", "lessons": ["A reusable lesson, only if there is one."], "evidence": ["file:docs/changed-page.md"], "task": {"id": "ISSUE-12", "status": "done"}, "docs_impact": "updated"}
```

- `status` is `success`, `partial`, `failed` or `no_lesson`. Use `lessons: []` when nothing is worth remembering; at most 10 lessons of 600 characters.
- `evidence`: `file:` only for a file that exists in this checkout, `id:` only for a memory record ID, `https://` for links, and `ref:` for everything else (commit SHAs, PRs, task numbers, other worktrees or outside paths). Unverifiable references are kept as `ref:`. `task` is optional and is only your report, never acceptance.
- When you change code, update the matching `docs/` topic page in the same change. Set `docs_impact` to `updated`, `none` (no documentation effect) or `needed`; otherwise a code change without docs is reported as docs debt.
- Never put secrets, personal data or raw logs in the block. Skip it for trivial replies.
- The hook saves the block as an unreviewed episode and adds a line to `docs/status/activity-log.md`; it never becomes an accepted fact without review.
<!-- dreamdocs:automation:end -->
