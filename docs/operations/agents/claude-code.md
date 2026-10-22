---
{"document":"agent-claude-code","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Claude Code adapter

**UNVERIFIED.** [adapters/claude-code/hook.py](../../../adapters/claude-code/hook.py) is built from the
documented Claude Code 2.1.273 hook payloads and tested only with recorded fixtures. No authenticated
Claude Code session has run it yet, so Claude Code stays unsupported until that run is recorded.

The adapter uses the same [shared lifecycle](../../../scripts/lifecycle.py) as the [Codex adapter](codex.md):
it never reads transcripts, never calls a model and never blocks or continues the agent.

| Event | What the hook does |
|---|---|
| `SessionStart` | Recalls the project briefing (recall without a query, up to 4000 characters) as `additionalContext` |
| `UserPromptSubmit` | Recalls memory related to the prompt when it has at least three meaningful words |
| `Stop` | Saves the turn from the last `dreamdocs-outcome` block, or writes a `no_lesson` receipt; does nothing when `stop_hook_active` is true |
| `StopFailure` | Treated as an interrupted turn: nothing is written |
| `SessionEnd` | Publishes queued captures when any exist |

Claude's `Stop` payload has no `turn_id`. The adapter uses `prompt_id` when present (documented as
a common field, seen on `UserPromptSubmit` and `StopFailure`, not yet seen on `Stop`), otherwise a
hash of the final message, so a repeated `Stop` for the same answer is saved once.

## Setup

`python -B scripts/dreamdocs.py setup --client claude-code` previews and `--apply` writes the hooks into
`.claude/settings.local.json`, Claude Code's project file that is not shared, because each handler holds
this computer's Python path. The shared `.claude/settings.json` is never changed. Handlers use exec form
(`command` plus `args`, no shell) with `${CLAUDE_PROJECT_DIR}` for the script path, so spaces need no
quoting. The outcome instruction block goes into `CLAUDE.md`. Setup adds `.claude/.gitignore` for the
local file when it creates it, and uninstall restores your files byte for byte when unchanged since setup.

## Still to verify after sign-in

- `Stop` and `SessionEnd` firing and their payloads, including `prompt_id` on `Stop`.
- Whether interactive sessions ask to review new or changed hooks.
- That `additionalContext` reaches the model in a real turn.
- The 1.5 s default `SessionEnd` budget with the configured 3 s timeout.
