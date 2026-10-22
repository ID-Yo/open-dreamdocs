---
{"document":"first-run","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# First run: automatic memory

Candidate 1.5.0-rc.1: consult the [support matrix](support-matrix.md). Codex has prior trusted-hook
runtime proof; final-candidate verification still applies. Claude Code remains experimental until
authentication and stable Stop identity/save/new-session recall are observed. These are release
gates, not optional substitutes for fixture tests. Use the [two-session demo](../../prompts/memory-demo.md).

This connects Codex to project memory. The documents work without it. Python 3.11 or newer and
Codex CLI are required. Claude Code can be set up with `--client claude-code`; its adapter is
[unverified](agents/claude-code.md) until an authenticated session has used it.

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
   python -B scripts/dreamdocs.py setup --apply --project-id my-project --client codex
   ```

   Setup writes only project files: `memory/automation.json`, Dreamdocs entries merged into
   `.codex/hooks.json` (your own hooks stay as they are), the outcome instruction block in
   `AGENTS.md` (your own rules stay as they are) and the manifest `memory/automation/install.json`.
   When setup creates `.codex/hooks.json` it also adds `.codex/.gitignore` so the file, which holds
   paths for this computer, is not committed; if your existing hooks file is tracked, setup warns.
   Running it again changes nothing. It never edits your user-level Codex config, never runs Codex and
   never installs a schedule.
3. Trust the hooks. Open Codex in the project, run `/hooks`, review the four Dreamdocs hooks and
   trust them, and trust the project's `.codex` folder if asked. Codex skips untrusted or changed hooks.
   Never use `--dangerously-bypass-hook-trust`.
   Codex treats a folder outside a Git repository as untrusted: `codex exec` refuses to run there
   ("Not inside a trusted directory") even after the hooks are trusted. Run `git init` in the project,
   or trust the directory in Codex; the setup preview warns when the folder is not in a repository.
4. Work normally. Ask for a meaningful task; the agent ends with a `dreamdocs-outcome` block and the
   `Stop` hook saves it. A new session receives the relevant memory at start. See the
   [Codex adapter](agents/codex.md) for what each hook does and its limits.

Setup cannot observe trust, so the manifest's trust/probe fields start pending. Doctor reports
capture readback, hook integrity, reported trust and fresh-session recall separately. A receipt
alone never proves client trust or recall. Supply separately observed source-backed evidence and
explicit `doctor --fix` only under the [health contract](memory-health.md); isolated `--smoke` tests
are not real-client evidence. The hook command contains absolute paths, so run setup again after
moving or copying the project folder. On Windows, Codex 0.147.0 runs hooks through PowerShell. The
command keeps the Python path unquoted and quotes only the hook script, which works in PowerShell and
cmd even when the project path has spaces and the drive has no 8.3 names. If the Python path itself
has spaces, setup uses the PowerShell form `& "...python.exe" ...` and warns that it will not run
from cmd. Both forms ran under Codex 0.147.0 on Windows.

To select Claude explicitly, preview `python -B scripts/dreamdocs.py setup --client claude-code`
and add `--apply` only after reviewing the plan and [Claude limitations](agents/claude-code.md).
The shipped exec-form configuration is documented; fixture success still does not establish
authenticated runtime behavior on the selected client.
Repeat `--client` to configure both adapters in one project; this does not prove both runtime paths.
Without stable prompt identity on Stop the Claude adapter warns and saves nothing.

For errors, run `python -B scripts/dreamdocs.py doctor` and follow the reported next action.
Unknown/unverified states return nonzero; do not clear locks just to obtain a green report.
Use [pinned upgrade/rollback](upgrading.md) for an older adopted project, and the [explicit executor](dreamer-execution.md)
for curation. No curation executor or scheduler is selected automatically.

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
