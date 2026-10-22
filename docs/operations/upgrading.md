---
{"document":"upgrading","status":"draft","owner":"<project-owner>","last_reviewed":null}
---

# Selected package upgrades

Run the **new reviewed package's** entry point with `--root <existing-project>`; an adopted v1.4.0
project has no `dreamdocs.py` of its own. Source bundles work offline and need no Git metadata at
the target. Nothing fetches a silent latest release or replaces remotes/history. The supported
legacy baseline is public v1.4.0, revision `26c7aff57be6ffb4ccd6287c979e3782a0a19b2a`.

```text
python -B <new-package>/scripts/dreamdocs.py --root <project> upgrade --source <new-package> --revision <reviewed-40-character-revision> --manifest-sha256 <independently-reviewed-manifest-hash> --from-version v1.4.0
```

Default and `--dry-run` print the complete collision map without writes. Review it, then repeat
with `--apply`. `--from-version v1.4.0` is required only for known legacy adoption without an
install manifest. Unknown-base overlaps and local edits/deletions of managed files are conflicts;
they are never silently reclassified as package-owned. Customized docs, templates, PROJECT,
originals, memory records/config/checkpoints and unrelated application files remain user-owned.
Only executable package assets, adapter assets and schema files are updated, plus the narrowly
merged setup instruction blocks, binding and project-local hooks. Changes outside an instruction
block are preserved. Edited managed instruction blocks or hook configurations defer the whole
update for explicit inspection/merge. Moving a worktree requires review of regenerated absolute
hook paths and renewed trust. Reinstall uses normal setup; uninstall retains user memory/docs.

## Source identity and release preparation

Upgrades add the exact pinned `memory/automation/README.md` and `receipts/README.md` scaffolds only
when missing, preserving existing user READMEs/notes. Existing scripts/README.md stays user-owned
so a legacy project does not gain broken links into new canonical pages it has not adopted.
The new validator checks the entire upgraded target before the new install manifest/version is
committed; validation failure leaves an interrupted journal, not applied success.

```text
python -B <new-package>/scripts/dreamdocs.py --root <project> rollback --backup .dreamdocs/backups/<transaction>
python -B <new-package>/scripts/dreamdocs.py --root <project> rollback --backup .dreamdocs/backups/<transaction> --apply
```

Rollback retains newly created compatibility READMEs as user data, including later edits, because
preserved post-upgrade receipts need those parent folders to remain valid under a legacy validator.
New transactions store backup payloads with `.bin` suffixes to avoid legacy validators interpreting
copied Markdown in private backups as active project documentation; older journal paths remain
readable. Memory and owner guidance are preserved. Full target validation also precedes rollback
success. Legacy v1.4.0 still loses automation capability on rollback; preserved data is not proof of
automatic lifecycle support that legacy never had.

A selected bundle contains `dreamdocs-release.json`: version 1, the exact upstream
`https://github.com/ID-Yo/open-dreamdocs`, full revision, package version, memory schema version
and a relative package-file SHA-256 map. A publisher can print this inventory with
`bundle-manifest --revision <revision>`. Review and distribute its exact bytes before deriving
the expected SHA-256. Obtain the expected upstream revision and manifest pin independently from
a trusted reviewed release/owner record. A hash calculated from an unreviewed download is **not**
publisher authentication. The updater checks those explicit external pins separately from the
bundle's self-declared identity and each file's checksum; it also compares the declared package
version with the source code constant without executing the incoming code. No downloaded source
is executed during preflight or staging. This is an explicit pinned offline workflow, not a
signature verification service or automatic upstream discovery.

Version-1 memory/config/install schemas are the only supported migration path. Skip-version
updates within that compatibility envelope compare installed/current/incoming hashes directly;
unsupported schemas stop before writes. There is no speculative data conversion. Upgrade never
changes models, installs companion products, enables schedules, calls a model or publishes data.

## Private transaction and recovery

Preflight refuses active or unresolved Dreamer/command locks, validates existing memory, checks
free space and checks every planned target. Apply takes the common writer lock and rechecks
target bytes, then stages exact before/after bytes under `.dreamdocs/backups/<timestamp>/` with
a versioned `journal.json`. A project-local ignore rule protects backups; inspect public exports
and never force-add them. Backups may contain private machine-local hook settings. All managed
writes are atomic per file with readback; the installed version is committed last after validation.
The operation is journaled, not a filesystem-wide atomic transaction.

Before any backup payload/journal publication, Git targets verify that the exact planned paths
are untracked and effectively ignored. This is rechecked under the operation lock for upgrade
and rollback. Existing owner ignore rules are preserved; negation overrides, tracked destinations
or unavailable Git verification refuse with a conflict before private bytes are published. A
missing local backup ignore file may be initialized and then checked. Plain non-Git copies remain
supported with a self-ignoring transaction directory; review private contents before future Git
adoption/export. Later owner rule changes and force-adds are not prevented by this point-in-time check.

No-space/permission failures do not claim a new installed version. An interruption can leave a
mixed package and a prepared/interrupted journal; a new upgrade refuses to run over that state.
Keep the backup and use explicit rollback/recovery. Never remove an active lock automatically.
Changed hooks reset trust/probe to pending; doctor configuration checks and synthetic smoke do not
replace actual client trust and fresh-session save/recall acceptance. Claude remains unverified
until an authenticated session proves its stable Stop identity and lifecycle behavior.
