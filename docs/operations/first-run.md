---
{"document":"first-run","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# First run: automatic memory

This connects Codex to project memory. The documents work without it. Python 3.11 or newer and
Codex CLI are required; Claude Code support is not available yet.

1. Preview the setup. Nothing is written:

   ```text
   python -B scripts/dreamdocs.py setup
   ```

   The plan shows the project folder, the Python interpreter, the hook command, each file it would
   create or update, the memory policy, warnings and how to remove it again. Setup stops with an exact
   next action on a conflict (for example an unreadable `.codex/hooks.json` or a binding for another
   project) or when Codex CLI is not installed.
2. Apply it:

   ```text
   python -B scripts/dreamdocs.py setup --apply [--project-id ID]
   ```

   Setup writes only project files: `memory/automation.json`, Dreamdocs entries merged into
   `.codex/hooks.json` (your own hooks stay as they are), the outcome instruction block in
   `AGENTS.md` (your own rules stay as they are) and the manifest `memory/automation/install.json`.
   Running it again changes nothing. It never edits your user-level Codex config, never runs Codex and
   never installs a schedule.
3. Trust the hooks. Open Codex in the project, run `/hooks`, review the four Dreamdocs hooks and
   trust them, and trust the project's `.codex` folder if asked. Codex skips untrusted or changed hooks.
   Never use `--dangerously-bypass-hook-trust`.
4. Work normally. Ask for a meaningful task; the agent ends with a `dreamdocs-outcome` block and the
   `Stop` hook saves it. A new session receives the relevant memory at start. See the
   [Codex adapter](agents/codex.md) for what each hook does and its limits.

Until a real trusted session has saved and recalled memory, the manifest keeps the trust and probe
states `pending`. The hook command contains absolute paths for this computer, so run setup again after
moving or copying the project folder.

## Remove

```text
python -B scripts/dreamdocs.py uninstall --apply
```

This removes the Dreamdocs hook entries, the instruction block, the binding and the manifest. Your
documents, memory records, receipts and other hooks stay. Without `--apply` it only lists the changes.

Setup keeps your file's newline style and inserts or removes only the instruction block. It saves the
original bytes of an existing `.codex/hooks.json` in the local, Git-ignored `.dreamdocs/` folder;
uninstall restores those bytes when the file is unchanged since setup. If you edited it afterwards,
uninstall removes only the Dreamdocs entries and keeps the rest of the content, without its formatting.
