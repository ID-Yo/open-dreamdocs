---
{"document":"agent-codex","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Codex adapter

[adapters/codex/hook.py](../../../adapters/codex/hook.py) connects Codex lifecycle hooks to the shared
[capture and recall commands](../automation-contract.md). It is installed per project by setup (#15) into
`.codex/hooks.json` and runs only after you review and trust the hooks in Codex. It never reads
transcripts, never calls a model and never blocks or continues the agent.

| Event | What the hook does | Output |
|---|---|---|
| `SessionStart` | Recalls the project briefing: recall without a query, so accepted facts and procedures, open contradictions and the most recent episodes (up to 4000 characters); topic selection happens at `UserPromptSubmit` | `additionalContext`, framed as untrusted data |
| `UserPromptSubmit` | Recalls memory related to the prompt when it has at least three meaningful words (up to 2000 characters, 3 episodes) | `additionalContext` or nothing |
| `Stop` | Saves the turn: the last `dreamdocs-outcome` block in the final message becomes an episode; without a block only a receipt (`no_lesson`) is written | `{}`, or a `systemMessage` when the capture was queued, refused or failed |
| `SessionEnd` | Publishes queued captures when any exist | nothing |

`Stop` is the durable save point. The hook writes the exact event to `memory/automation/events/`
before capture, redelivers those bytes on a retry, skips turns that already have a receipt and does
nothing when `stop_hook_active` is true. Credential-like or invalid content is refused before
anything is written. A malformed block falls back to a receipt with a warning; lessons come only from
the block, as described in [the instruction block](../../../adapters/outcome-block.md).

## Status

Codex CLI 0.147.0 on Windows delivers these four events and shows `SessionStart`
`additionalContext` to the model (verifier probe, run with the trust bypass flag). The adapter
itself is tested only with recorded payloads; an end-to-end run with trusted project hooks is still
required before Codex is marked supported. Codex Desktop is untested.

## Limits

- Project hooks run only after the project `.codex/` layer and each hook are trusted; changed hooks
  need new trust. Never use `--dangerously-bypass-hook-trust` for real use.
- Codex clamps `SessionEnd` to 3 seconds; a killed hook that held the writer lock leaves it for
  manual recovery.
- Turns without a block save no summary text. The agent must emit the block for lessons to be kept.
