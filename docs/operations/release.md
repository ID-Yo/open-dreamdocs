---
{"document":"release","status":"draft","owner":"<project-owner>","last_reviewed":"2026-10-22"}
---

# Reproducible candidate and release gates

Version 1.5.0-rc.6 is prepared for review. It is **not approved for publication as a working
dual-client release**. Actual Claude save/new-session recall, client switching and final exact-
candidate clean-room acceptance remain release gates. See the [support matrix](support-matrix.md).
Tests or setup success cannot substitute for those observations; do not close the epic from them.

## Clean source artifact

Use a clean public checkout at the full exact reviewed commit. The package helper audits tracked
snapshot paths and all reachable commit-history object paths/blobs, then creates a deterministic
ZIP from committed bytes. It does not copy untracked/ignored files or any .git history, push, tag,
publish or authorize a release. It refuses tracked edits, private/unapproved paths, links/submodules,
real credential-pattern matches, populated memory/config, originals or a changed material index.
Known synthetic fixtures remain synthetic; secret checks report object IDs, never matched values.
The marker-only unsafe-input fixture is excepted by its exact reviewed whole-blob SHA-256
`43da2685a25718c3b2a6dd96cc276c265a62134d57c6826467bd6ec331718cb7`; it contains no key material.
No test directory is exempt. Any changed bytes need new review and real credentials still fail.
The source-history audit also checks reachable commit messages and every local annotated tag
message for those credential patterns. Every historical human-materials/README.md version must
match the reviewed empty-index privacy rule, not just the tip. A later clean snapshot does not
erase private history; findings block packaging and report only object IDs, never matched content.

```text
python -B scripts/release_package.py --root . --revision FULL_REVIEWED_COMMIT
python -B scripts/release_package.py --root . --revision FULL_REVIEWED_COMMIT --output PATH_OUTSIDE_SOURCE/new-candidate.zip
```

The output must be new and outside the source tree. The ZIP has fixed member dates/order/permissions
and contains release-package.json (exact full inventory, source revision, no-history declaration)
and dreamdocs-release.json (package-owned updater hashes). Rebuilding the same source with the same
Python/zlib runtime gives byte-identical ZIP output. Record that runtime and both archive/manifest
hashes. Hash agreement is integrity, not publisher authentication; get the expected reviewed source
revision and manifest pin independently from the trusted release/owner record.

Run the full suite in both the exact Git source and a fresh extraction of the generated ZIP.
The ZIP intentionally contains no Git history, so legacy-upgrade tests requiring
`git archive 26c7aff57be6ffb4ccd6287c979e3782a0a19b2a` explicitly skips when that external
historical fixture is unavailable. These skips are not upgrade acceptance: the full Git-source run
must exercise them before release. All other tests, setup assets, clean memory/config and link/schema
checks must pass from the extracted artifact. Record pass/skip counts separately.

Audit scope is bounded to 20,000 reachable objects, 4 MiB per history blob and 100 MB overall;
larger repositories need an independent audit. Pattern checks do not prove the absence of every
kind of secret or personal information. Independent review must inspect exact inventory/content
and public provenance. If private history is found, preserve it privately and prepare a separately
reviewed sanitized snapshot/new public history; do not rewrite or publish the private history.
Do not copy a used checkout, CBM team/agent state, machine hooks, .dreamdocs, logs, backups, events,
receipts, accepted owner records or populated human-material indexes into the distribution.

## Download-to-memory acceptance matrix

For each required client, start from a freshly extracted ZIP using only shipped guides. Record
exact source, archive/manifest hashes, OS, Python/client versions, account/auth route and independent
candidate/reviewer/Manager evidence. Keep private session identifiers/reports in an explicitly
private acceptance destination; publish only reviewed summaries.

| Gate | Required observed result |
|---|---|
| Clean package | File inventory/checksums agree, no history/private runtime or CBM artifacts; all tests/links/schemas pass |
| Codex real lifecycle | Review/trust hooks, real outcome automatically persists episode+receipt, new session answers demo marker without tools |
| Claude real lifecycle | Owner-authenticated turn exposes stable Stop identity and automatically saves; separate new session recalls without tools |
| Client switching | Both directions recall the same project evidence automatically with no manual save injection |
| Health/recovery | A real failed/queued capture is visible; original event retries safely after repair, no false success or live-lock takeover |
| Curation | Explicit executor reviews inputs, produces only proposals, result/report/checkpoint hashes read back; no automatic promotion |
| Existing project | Reviewed pinned upgrade preserves customized docs/memory; rollback preserves new memory/refuses later edits; real automatic save/recall probes pass after upgrade AND rollback between automation versions |
| Final artifact | Independently reviewed exact commit, main/tag and downloaded archive inventories match; no silent newer content |

Claude authentication and a verified Stop identity are unsupported prerequisites until actually
observed. Do not work around them with a final-message hash, direct capture call, fabricated receipt
or an outcome fixture. The [demo](../../prompts/memory-demo.md) is a test instruction, not preloaded
memory. An intentionally nonzero doctor result for unknown integration health is honest evidence.

Optional scheduling is a separate owner opt-in. Do not install it merely to complete packaging.
Nightly, reboot/offline catch-up or unattended claims need a real installed trigger/executor test
and documented backend limits. Hosts that are off cannot execute. No default model call or telemetry.

## Publication handoff

The maintainer supplies candidate SHA, local suite/link results, source/archive/runtime manifest
hashes, privacy/history audit findings and the completed real acceptance matrix. Code Reviewer and
QA assess that exact candidate; Manager/owner owns acceptance and publication. Until all nonoptional
gates pass, retain candidate status. After publication, download the actual public artifact and
compare its inventory/behavior with the accepted package; a local ZIP alone does not prove it.
