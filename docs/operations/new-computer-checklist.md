---
{"document":"new-computer-checklist","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Setting up on a new computer

Use this checklist for a new machine or a new project. It adds the practical steps around
[first run](first-run.md); read [how it works](how-it-works.md) first if you want the overview.

## Before you start

- Python 3.11 or newer on the PATH (`python --version`). The tools use only the standard library.
- Git, and the project folder inside a Git repository (`git init` is enough). Codex treats a folder
  outside a repository as untrusted.
- Codex CLI installed and signed in. You need it once per project to review the hooks (see below).
- A reviewed Dreamdocs package: a release ZIP or a clean clone of the revision you intend to use.
  Check the revision and archive hash against the release you were told to use.

## New project

1. Extract or clone the package into the project's permanent folder. The hook command stores absolute
   paths, so do not set up in a temporary folder and move it afterwards.
2. Preview, then apply:

   ```text
   python -B scripts/dreamdocs.py setup
   python -B scripts/dreamdocs.py setup --apply --project-id my-project --client codex
   ```

3. Trust the hooks (next section).
4. Fill in `PROJECT.md` and `docs/overview/platform.md`.
   Optionally let Dreamdocs index your own files in `human-materials/`:
   `python -B scripts/dreamdocs.py materials mode summarize` (see [Human Materials indexing](human-materials-indexing.md);
   PDF needs `pip install pypdf`).
5. Run `python -B scripts/dreamdocs.py doctor` and the [two-session demo](../../prompts/memory-demo.md).

## Existing project

Follow [selective adoption](adopting-dreamdocs.md) first: add only missing package files, keep your
own rules, then run `setup` as above from the project.

## Project already on v1.4.0

Run the *new* package's entry point against the project with `--root` and the pinned values from
[upgrading](upgrading.md). Preview with `--dry-run`, resolve each reported conflict, then `--apply`:

```text
python -B <new-package>/scripts/dreamdocs.py --root <project> upgrade --from-version v1.4.0 \
  --source <extracted-package-folder> --revision <40-character-revision> --manifest-sha256 <pinned-hash>
```

- `--source` is an extracted folder that contains `dreamdocs-release.json`, not the ZIP itself.
- A conflict on a package script means the local copy differs from the v1.4.0 baseline or is missing.
  Compare it with the baseline, keep a backup of your version, then replace it with the package copy and
  rerun the dry-run. Nothing is overwritten silently.
- If the result says *interrupted*, the project keeps a journal under `.dreamdocs/backups/`. Do not
  start another upgrade over it. Use `rollback --backup` to inspect or revert; if rollback reports a
  changed managed file, merge that file explicitly first.

## Trust the hooks

Hooks do nothing until Codex trusts them.

1. Open a terminal in the project folder and start Codex CLI: `codex`.
2. Codex loads a project's `.codex` folder only for a trusted project. Answer the trust prompt for
   the project folder with *trust*; this writes a `trust_level = "trusted"` entry for the project to
   your user-level Codex configuration. Hooks in an untrusted project are skipped silently, even when
   each hook is approved.
3. Run `/hooks`, review the four Dreamdocs hooks (`SessionStart`, `UserPromptSubmit`, `Stop`,
   `SessionEnd`) and trust them.
4. Quit. Trust is stored per project in your user-level Codex configuration, so Codex Desktop and the
   CLI see the same approval on that computer. One Windows Desktop session has been observed
   capturing episodes after trust was granted, but Desktop is not a tested release target
   ([support matrix](support-matrix.md)). The `/hooks` command is a CLI command; Desktop may not offer it.

Repeat this for every project, and again after every setup or upgrade that changes the hooks.

## Verify

| Check | How | Good result |
|---|---|---|
| Install integrity | `python -B scripts/dreamdocs.py doctor` | `hook_config: intact`; capture, trust and recall may still read *unknown* |
| Capture | Finish a real task | A new `auto-evt-*` file in `memory/episodes/` and a receipt |
| Recall | Open a new session and ask about the saved topic | The saved content appears without reading files |

If the checks pass, the project is working. If a turn shows the outcome block in chat but nothing was
saved, the hooks are not trusted yet.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Outcome block appears, no episode saved | The project is not trusted, the hooks are not trusted, or setup was not applied | Trust the project folder and the hooks in the CLI (`/hooks`); run `doctor` |
| `/hooks` does nothing in the desktop app | It is a CLI command | Run it from a terminal with `codex` |
| Hooks stopped working after moving or copying the folder | Absolute paths in `.codex/hooks.json` | Run `setup --apply` again, then trust again |
| Codex refuses to run: not inside a trusted directory | Folder is not a Git repository | `git init`, or trust the directory in Codex |
| Setup stops with a missing-assets conflict | Target lacks the package files | Extract the package into the project, or follow selective adoption |
| Upgrade says unknown installed base | Project has no install manifest | Use `--from-version v1.4.0` only for a known v1.4.0 adoption |
| Upgrade is blocked by an unfinished transaction | A previous upgrade was interrupted | Inspect the journal and use `rollback`; never delete a lock by hand |

## Keep it updated

Updates are explicit and pinned; nothing fetches a latest release by itself. When a new release
arrives, follow [upgrading](upgrading.md), then trust the hooks again and rerun the verification.
