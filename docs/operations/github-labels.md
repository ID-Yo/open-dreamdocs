---
{"document":"github-labels","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Reusable GitHub Labels

Use the [eight-definition JSON template](../../templates/github-labels.json) as a
small reusable vocabulary. It installs nothing itself. The owner names a maintainer
(normally the project Manager), one target repository and the existing workflow
authority. Preserve the chosen local/GitHub tracking mode and existing aliases.

For projects using GitHub issue state tracking with the Agent Monitor (CBM #343),
use the [task-state labels template](../../templates/task-state-labels.json).
It defines the exact seven task-state labels used to track and monitor execution state.

| Category | Label | Description | Hex |
|---|---|---|---|
| Work size | `type:epic` | Large outcome delivered through linked stories or tasks. | `5319E7` |
| Work size | `type:story` | One user or participant outcome with acceptance criteria. | `7057FF` |
| Work size | `type:task` | One actionable deliverable with a clear completion check. | `BFD4F2` |
| Workflow | `status:in-progress` | Work is actively being performed by an assigned owner. | `1D76DB` |
| Workflow | `status:review` | Deliverable is ready and waiting for review or acceptance. | `FBCA04` |
| Workflow | `status:blocked` | Progress needs a named dependency or decision to be resolved. | `B60205` |
| Priority | `priority:high` | Prioritize ahead of normal work; owner records why. | `D93F0B` |
| Planning | `plan:future` | Uncommitted future idea; not approved or scheduled for delivery. | `C5DEF5` |

## Task-state labels (Agent Monitor compatible)

The file [`templates/task-state-labels.json`](../../templates/task-state-labels.json) provides
the canonical seven-label vocabulary for tracking agent and project tasks. Every open work
issue carries exactly one of these state labels; closed issues indicate completed or rejected work.

| Label | Color | Description | Meaning and rules |
|---|---|---|---|
| `state:ready` | `BFD4F2` | Start approved and ready; check dependencies before dispatch | Work is approved to start and ready for assignment. Check prerequisites before dispatching. |
| `state:active` | `0E8A16` | Approved work actually in progress with a started executor | An executor has started actual work. Queue or dispatch alone is not active. |
| `state:review` | `FBCA04` | Candidate under independent review or QA | Implementation candidate delivered; awaiting independent code review or QA verification. |
| `state:blocked` | `B60205` | Blocked on a technical, dependency or capacity condition recorded in the issue | Blocked on technical, tool, dependency or capacity conditions that do NOT wait on the owner. |
| `state:needs-owner` | `D93F0B` | Blocked: waits on the owner; reason, resume condition and next check recorded in the issue | Blocked specifically waiting on owner action, approval or decision. |
| `state:backlog` | `EDEDED` | Recorded but not approved or scheduled; no execution expectation | Recorded item without approval to start; no execution expectation. |
| `future` | `C5DEF5` | Not scheduled; no execution expectation | Unscheduled future concept; no execution expectation. |

### Task state management rules

- **Manager authority**: The project Manager exclusively manages and updates these labels across task handoffs and state changes.
- **Blocked requirements**: Whenever setting `state:blocked` or `state:needs-owner`, the issue must explicitly record: (1) blocker reason, (2) unblock owner, (3) resume condition, and (4) next check time.
- **Blocked vs. needs-owner**: Use `state:needs-owner` exclusively when progress depends directly on the project owner (e.g., owner decision, external credential, financial approval). Use `state:blocked` for technical impediments, tool outages, worker capacity, or upstream dependencies. Note: older Agent Monitor versions recognize only `state:needs-owner` as the blocked state.
- **Explicit user command**: Nothing writes to GitHub automatically. Labels are created only when the user explicitly issues the creation command.

### Creating task-state labels in your repository

Before creating labels, inspect or back up any existing labels in your repository:

```bash
gh label list --repo OWNER/REPO --json name,color,description
```

> **Warning on `--force` overwrite**:
> The commands below use `--force` to create missing labels. On a name collision, `--force` **overwrites** an existing label's color and description with the template values. If your repository already has its own label definitions or custom styling that you must preserve without overwriting, do not use `--force`; use the conflict-refusing [preservation-first import](#export-and-preservation-first-import) procedure below instead.

You can create these labels idempotently in your repository using GitHub CLI (`gh`):

```bash
# Using gh label create --force (idempotent: creates missing labels, or overwrites existing color and description)
gh label create state:ready --color BFD4F2 --description "Start approved and ready; check dependencies before dispatch" --force
gh label create state:active --color 0E8A16 --description "Approved work actually in progress with a started executor" --force
gh label create state:review --color FBCA04 --description "Candidate under independent review or QA" --force
gh label create state:blocked --color B60205 --description "Blocked on a technical, dependency or capacity condition recorded in the issue" --force
gh label create state:needs-owner --color D93F0B --description "Blocked: waits on the owner; reason, resume condition and next check recorded in the issue" --force
gh label create state:backlog --color EDEDED --description "Recorded but not approved or scheduled; no execution expectation" --force
gh label create future --color C5DEF5 --description "Not scheduled; no execution expectation" --force
```

Or in PowerShell iterating over `templates/task-state-labels.json`:

```powershell
$TargetRepo = "OWNER/REPO"  # Replace with your target repo. Warning: --force overwrites matching labels in-place.
$Labels = Get-Content -Raw -LiteralPath "templates/task-state-labels.json" | ConvertFrom-Json
foreach ($label in $Labels) {
    gh label create $label.name --color $label.color --description $label.description --repo $TargetRepo --force
}
```

### When to use each import path

- **Forced path (`--force`)**: Best for fresh or empty repositories, or projects that want their issue labels aligned exactly to the canonical Dreamdocs/CBM Monitor task-state standard regardless of previous local definitions.
- **Preservation-first path**: Best for established repositories with existing workflows, colors, or descriptions. It exports a backup (`labels-before.json`), compares metadata, creates only missing labels, and halts with an explicit error on any metadata conflict instead of overwriting existing data.

## Combinations and meaning

- After triage, exactly one `type:*` per issue. A story is a user/participant outcome;
  a task is a concrete verifiable deliverable, also in noncommercial projects.
  Standalone tasks are valid; do not force three levels for small work.
- At most one `status:*` and one `priority:*`. No priority label means normal.
  Accepted open work without status is awaiting scheduling/capacity (backlog).
- `plan:future` is an uncommitted idea, not accepted backlog; it may have an idea
  steward/review trigger but no implementation commitment. Do not combine it with
  `status:*`. Remove it and record acceptance before implementation starts.
- Blocked work names an impediment, responsible person and unblock condition.
  Paused means accepted work deliberately suspended with a revisit trigger; record
  that in its body. Neither paused nor blocked means future. No paused label is
  installed by this baseline. No label grants approval to build, publish or spend.
- If GitHub Projects owns workflow, omit all three `status:*` definitions and
  applications; use its Status field. If a native Priority or issue-type field
  already owns those meanings, omit duplicate label fields from the reviewed
  project selection. Do not maintain parallel sources of truth.
- GitHub open/closed and closure reason express completion/rejection: no done/closed
  labels. Clear active status labels on closure. Colors help scanning; words carry meaning.
- Keep existing `bug`, `enhancement`, `documentation`, `question` and equivalents
  for the nature of work, separate from size. Research/decision can be clear issue
  titles/body sections until filtering warrants optional definitions. No extra
  nature/domain labels are installed. Avoid creating synonyms for accepted labels.
- PRs describe their own scope, not their parent's `type:epic`. A one-deliverable
  PR may use `type:task` and existing `documentation`. Draft/review/merged already
  convey PR workflow; omit routine status labels on PRs.

## Hierarchy and examples (illustrative, not created)

Issue #100 “Run a community workshop”: `type:epic`, `priority:high`.
Its native sub-issue #101 “Participants can register”: `type:story`.
That issue's sub-issue #102 “Write registration instructions”: `type:task`,
existing `documentation`, and `status:in-progress` only if labels own status.
Each issue has its own owner, parent link and acceptance checks.
PR #103 says `Closes #102`, `Refs #101, #100`; it does not close the whole epic.
Issue #104 “Consider an autumn series”: `type:epic`, `plan:future`.

Use GitHub Create/Add existing sub-issue UI and verify the parent relation. Labels
alone never create hierarchy. If native sub-issues are unavailable, explicitly
record parent links/linked checklists as manual relationships. Epic/story owners
verify aggregate acceptance independently from the completion of one child.

## Export and preservation-first import

The UTF-8 JSON array uses only `name`, `description`, `color`. Descriptions are at
most 100 characters; colors have six hex digits without `#`. Short lowercase ASCII
names are this template's convention, not a claim of GitHub's maximum name limit.
The current token lacked `read:project` when checked on 2026-10-14; do not infer that
no Project exists. Ask the owner which authority already applies; do not change scopes.

Use existing authenticated GitHub CLI and PowerShell 7, without new dependencies.
The example defaults to dry-run. Set an explicitly approved target/status authority.
Export labels before changing definitions; keep backups private if descriptions
are sensitive. Review aliases first; if accepted names differ, make a reviewed
per-project JSON selection using those names, not new synonyms. Leave the
reusable template unchanged. Optional fields owned by Projects should be omitted.

```powershell
$TargetRepo = $null       # Explicit OWNER/REPO approved by owner
$StatusAuthority = $null  # Explicit 'labels' or 'projects'
$Apply = $false           # Change only after dry-run review and approval
$Template = 'templates/github-labels.json' # Or reviewed project selection
$Backup = 'labels-before.json' # Must not exist; retain outside public commits
if ($TargetRepo -notmatch '^[^/]+/[^/]+$') { throw 'Choose one target repository' }
if ($StatusAuthority -notin @('labels','projects')) { throw 'Choose status authority' }
if (Test-Path -LiteralPath $Backup) { throw 'Choose a new backup filename' }
$desired = @(Get-Content -Raw -LiteralPath $Template | ConvertFrom-Json)
if ($desired.Count -eq 0) { throw 'Empty label selection' }
$names = @{}
foreach ($label in $desired) {
    if ([string]::IsNullOrWhiteSpace($label.name) -or $label.name.Length -gt 40 -or
        $label.description.Length -gt 100 -or $label.color -notmatch '^[0-9A-Fa-f]{6}$') {
        throw 'Invalid template metadata'
    }
    if ($names.ContainsKey($label.name)) { throw 'Duplicate label name' }
    $names[$label.name] = $true
}
if ($StatusAuthority -eq 'projects') {
    $desired = @($desired | Where-Object { $_.name -notlike 'status:*' })
}
$raw = gh api --paginate --slurp "repos/$TargetRepo/labels?per_page=100"
if ($LASTEXITCODE) { throw 'Cannot read target inventory' }
$pages = @($raw | ConvertFrom-Json)
$current = @(foreach ($page in $pages) { foreach ($label in $page) { $label } })
ConvertTo-Json -InputObject @($current | Select-Object name,description,color) |
    Set-Content -Encoding utf8 -LiteralPath $Backup -ErrorAction Stop
$creates = @()
foreach ($label in $desired) {
    $existing = @($current | Where-Object { $_.name -ieq $label.name })
    if ($existing.Count -eq 0) {
        $creates += $label
        Write-Output "CREATE $($label.name)"
    } elseif ($existing.Count -ne 1 -or
              [string]$existing[0].description -cne [string]$label.description -or
              $existing[0].color -ine $label.color) {
        throw "Metadata conflict; review without overwriting: $($label.name)"
    } else { Write-Output "UNCHANGED $($label.name)" }
}
if ($Apply) {
    foreach ($label in $creates) {
        gh label create $label.name --description $label.description --color $label.color --repo $TargetRepo
        if ($LASTEXITCODE) { throw 'Stopped: re-read remote state before retrying' }
    }
} else { Write-Output 'Dry-run only; no labels changed.' }
```

After apply, rerun a fresh inventory/dry-run with a new backup filename: no creates
or conflicts should remain. Reruns are idempotent for label definitions. If create
times out or returns a validation error, stop and re-read before retrying: it may
already have succeeded. Avoid unconditional `--force`, broad cloning or deletion.

Installation never relabels issues/PRs. Migration needs a separate approved old-to-new
mapping, affected issue/PR inventory and association backup. Add replacements without
replacing unrelated labels; verify before retiring any association/definition.
Deleting a label removes its associations: preserve defaults/history until explicit
approval. The maintainer checks combinations at triage/handoffs and proposes changes.

## Official references (checked 2026-10-14)

- [Scope, permissions and deletion](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/managing-labels)
- [REST label metadata and additive versus replacement operations](https://docs.github.com/en/rest/issues/labels)
- [Native sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
- [CLI label creation](https://cli.github.com/manual/gh_label_create)
