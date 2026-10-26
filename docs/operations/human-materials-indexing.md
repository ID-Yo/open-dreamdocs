# Human Materials indexing

Dreamdocs can keep [`human-materials/README.md`](../../human-materials/README.md) up to date by itself, so agents read a short summary first and open an original only when a task needs it.

## Turn it on

The owner decides per project. The choice is stored in `memory/config.json` under `human_materials.indexing`; when the key is missing, indexing is `off`.

| Mode | What happens |
|---|---|
| `off` | Nothing runs. `doctor` reports files without index rows. |
| `inventory` | Files are hashed. New files get an `unread` row, moved files keep their row with the new link, rows of deleted files are removed. Content is never read. |
| `summarize` | Inventory, plus each queued file is read and summarized by an isolated Codex run. The row gets a summary, a "Read the original when" hint, topical tags, a `category:` tag, a `sensitivity:` tag, status `ai-draft` and today's date. |

```text
python -B scripts/dreamdocs.py materials mode summarize
python -B scripts/dreamdocs.py materials index --apply     # run now
python -B scripts/dreamdocs.py materials status
```

Optional settings in the same object: `exclude` (glob list never read), `max_file_bytes` (default 20 MiB), `max_chars` per file (default 20000), `max_files_per_run` (default 10), `min_hours_between_runs` (default 6) and `timeout_seconds` per file (default 300).

## When it runs

- **Session start.** The Codex or Claude Code SessionStart hook starts one background run when the last run is older than `min_hours_between_runs`. The session is not delayed.
- **Dreamer.** Every `dreamer run` (manual or scheduled) indexes first and reports the result under `materials`; an indexing failure never blocks memory curation.
- **On demand** with `materials index --apply`.

A lock in `.dreamdocs/` prevents two runs at once. Files left over from the per-run budget wait for the next run.

Each prepared Dreamer execution receipt at `.dreamdocs/dreamer-runs/RUN_ID.json` keeps
its own `materials` summary: state, trigger, finish time and counts (including failed,
skipped and remaining files). It contains no original filenames, content or error text.
`dreamer status` and the `doctor` Dreamer section show that receipt's summary, even
after a later session-start index run replaces the current indexing state. Indexing
errors or busy/off states remain separate from curation success. Older receipts
without this summary show `materials: null`; no historical result is inferred.

## How the summary is made

Text, Markdown, CSV, JSON and similar files, DOCX, PPTX, XLSX and OpenDocument are read with the Python standard library. PDF needs the optional `pypdf` package or `pdftotext` on PATH. Images are attached to the Codex call. Other formats (audio, video, archives) are marked `unparseable` with the reason.

The summarizer is `codex exec` started in an empty temporary folder with a read-only sandbox, `--ephemeral`, hooks, memories, apps, plugins and tools disabled, and a fixed JSON output schema. The document is passed as untrusted data. It uses the Codex login of this computer, so file content goes to that account and nowhere else. The Codex CLI is looked up in `DREAMDOCS_CODEX`, then on PATH, then (on Windows) in the Codex desktop app package folder, which scheduled tasks cannot see on PATH.

## Privacy and review rules

- Originals are only read. They are never moved, renamed, deleted, uploaded or added to Git.
- Never read: `.env*`, key, certificate and keystore files, `id_rsa*`, names containing `password`, `secret`, `credential` or `private-no-ai`, the owner's `exclude` list, files above `max_file_bytes`, and files with credential-like content.
- `ai-draft` rows are unverified. A person changes the status to `reviewed` after checking.
- Rows marked `reviewed` or `partial` are never overwritten. When such a file changes, the new summary is stored as a proposal in `.dreamdocs/human-materials-state.json` and `doctor` reports `materials_review_proposals`.
- The populated index stays private; public export rules in the index README still apply.

## How agents use it

Recall adds matching material summaries to the untrusted context of a prompt, and a one-line count at session start. Agents read the summary, decide whether the original matters, and open it only then.

