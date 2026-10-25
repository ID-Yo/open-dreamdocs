"""Prepare private, source-bound documentation proposals. Never apply or promote canonical edits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_contract as ac
import human_materials as hm
import project_memory as pm
import task_continuity as tc

POLICY = ".dreamdocs/documentation-policy.json"
FOLDER = ".dreamdocs/documentation-refresh"
INDEX, STATUS = "docs/00-index.md", "docs/status/current-state.md"
CLASSES = {"code_fact", "config_fact", "runtime_observation", "reviewed_research", "episode", "hypothesis", "unknown"}
REQUEST_FIELDS = {"version", "project_id", "task_id", "candidate", "task_snapshot_sha256", "title", "sources", "changes", "human_inventory", "dreamer_run_id"}


def path_name(value):
    pm.require(isinstance(value, str) and value and "\\" not in value and ":" not in value
               and not any(ord(c) < 32 for c in value), "invalid relative path")
    path = PurePosixPath(value)
    pm.require(not path.is_absolute() and ".." not in path.parts and path.as_posix() == value, "unsafe relative path")
    pm.require(not any(p in pm.PRUNE for p in path.parts), "tool/dependency path is outside refresh scope")
    return value


def fields(value, expected):
    pm.require(isinstance(value, dict) and set(value) == set(expected), "unexpected or missing fields")


def text(value, limit=4000):
    pm.require(isinstance(value, str) and value.strip() and len(value) <= limit, "expected bounded nonempty text")
    return value


def digest(value):
    pm.require(isinstance(value, str) and ac.SHA256.fullmatch(value), "expected SHA-256")
    return value


def readable_input(relative):
    """Also constrain untrusted sidecar dependencies before a recheck hashes them."""
    path_name(relative)
    lowered = relative.casefold()
    pm.require((not lowered.startswith("human-materials/") or relative == "human-materials/README.md")
               and not any(p.casefold().startswith(".env") for p in PurePosixPath(relative).parts)
               and not lowered.startswith(("memory/automation/", "memory/dreamer/work/", "memory/dreamer/proposals/")),
               "originals, credentials and raw/uncommitted runtime data cannot be read")


def links(path, content):
    result = set()
    for target in re.findall(r"\]\(([^)]+)\)", re.sub(r"```.*?```", "", content, flags=re.S)):
        url = urlsplit(target.strip("<>"))
        if not url.scheme and not url.netloc and url.path:
            relative = (PurePosixPath(path).parent / unquote(url.path)).as_posix()
            # Resolve only documentation-local links; do not open their targets here.
            parts = []
            for part in PurePosixPath(relative).parts:
                if part == "..":
                    if parts:
                        parts.pop()
                elif part != ".":
                    parts.append(part)
            result.add("/".join(parts))
    return result


def build(root, request, created_at=None):
    fields(request, REQUEST_FIELDS)
    pm.require(type(request["version"]) is int and request["version"] == 1, "unsupported refresh request version")
    pm.require(type(request["human_inventory"]) is bool, "human_inventory must be explicit boolean")
    text(request["title"], 200)
    pm.require("\n" not in request["title"] and "\r" not in request["title"], "title must fit one line")
    pm.require(not ac.SECRET.search(ac.canonical(request)), "credential-like content refused")
    pm.require(len(ac.canonical(request)) <= 131072, "refresh request exceeds 128 KiB")
    dependencies, blobs = {}, {}

    def read(relative, expected=None, absent=False):
        readable_input(relative)
        path = pm.confined(root, relative)
        if absent and not path.exists():
            raw = None
        else:
            pm.require(path.is_file() and path.stat().st_size <= pm.SOURCE_HASH_LIMIT, "missing or oversized refresh input: " + relative)
            raw = path.read_bytes()
        sha = pm.digest(raw) if raw is not None else None
        if expected is not None:
            pm.require(sha == digest(expected), "stale revision: " + relative)
        dependencies[relative], blobs[relative] = sha, raw
        return raw

    policy = json.loads(read(POLICY), object_pairs_hook=pm.unique_keys)
    fields(policy, {"version", "project_id", "manager", "task_file", "allowed_targets", "human_inventory"})
    pm.require(type(policy["version"]) is int and policy["version"] == 1 and type(policy["human_inventory"]) is bool, "unsupported documentation policy")
    bound = json.loads(read("memory/automation.json"), object_pairs_hook=pm.unique_keys)
    ac.validate_binding(bound)
    pm.require(policy["project_id"] == request["project_id"] == bound["project_id"], "project identity mismatch")
    pm.require(isinstance(policy["allowed_targets"], list) and all(isinstance(p, str) for p in policy["allowed_targets"]), "allowed_targets must be explicit paths")
    allowed = set(policy["allowed_targets"])
    for relative in allowed:
        path_name(relative)
        pm.require(relative.startswith("docs/") and relative.endswith(".md") and not relative.startswith("docs/governance/") and not relative.endswith("/AGENTS.md"), "policy cannot authorize governance or agent-rule changes")
    task_file = path_name(policy["task_file"])
    pm.require(task_file.startswith(".dreamdocs/"), "task snapshot must have a private project-local destination")
    snapshot = json.loads(read(task_file, digest(request["task_snapshot_sha256"])), object_pairs_hook=pm.unique_keys)
    pm.require(isinstance(snapshot, dict) and isinstance(snapshot.get("tasks"), list), "invalid task snapshot")
    tasks = [t for t in snapshot["tasks"] if isinstance(t, dict) and t.get("id") == request["task_id"]]
    pm.require(len(tasks) == 1, "one exact authoritative task required")
    task = tasks[0]
    pm.require(not ac.SECRET.search(ac.canonical(task)), "credential-like task evidence refused")
    pm.require(task.get("status") == "done" and task.get("manager") == policy["manager"], "task is not accepted by the configured Manager")
    audit = tc.check({**snapshot, "tasks": tasks})
    pm.require(audit["ok"], "task acceptance/continuity evidence is invalid: " + ", ".join(f["code"] for f in audit["findings"]))
    pm.require(task["candidate"]["id"] == request["candidate"], "accepted candidate revision mismatch")
    source_map = task["candidate"].get("source_hashes")
    pm.require(isinstance(source_map, dict) and source_map, "accepted candidate requires exact source_hashes; an episode or receipt alone is not acceptance")
    sources = request["sources"]
    pm.require(isinstance(sources, list) and 0 < len(sources) <= 20, "provide 1..20 selected sources")
    source_paths = set()
    for source in sources:
        fields(source, {"path", "sha256", "classification"})
        relative = path_name(source["path"])
        pm.require(relative not in source_paths, "duplicate source")
        lowered = relative.casefold()
        pm.require(not lowered.startswith(("human-materials/", "memory/automation/", "memory/dreamer/work/", "memory/dreamer/proposals/"))
                   and not any(part.casefold().startswith(".env") for part in PurePosixPath(relative).parts), "originals, raw events, credentials and uncommitted work are not readable refresh sources")
        if lowered.startswith("memory/dreamer/"):
            pm.require(request["dreamer_run_id"] is not None and relative == "memory/dreamer/reports/" + request["dreamer_run_id"] + ".json", "only the explicitly committed Dreamer report can be a source")
        pm.require(isinstance(source["classification"], str) and source["classification"] in CLASSES, "unknown evidence classification")
        pm.require(source_map.get(relative) == digest(source["sha256"]), "source is not bound to the accepted candidate: " + relative)
        raw = read(relative, source["sha256"])
        if relative.startswith("memory/episodes/"):
            meta = pm.metadata(raw.decode("utf-8"))
            pm.validate_record(meta, "episodes")
            pm.require(meta["project"] == request["project_id"], "foreign episode")
        source_paths.add(relative)
    run = request["dreamer_run_id"]
    if run is not None:
        pm.require(isinstance(run, str) and pm.IDENTIFIER.fullmatch(run), "invalid Dreamer run identity")
        state = json.loads(read("memory/dreamer/state.json"), object_pairs_hook=pm.unique_keys)
        report_path = "memory/dreamer/reports/" + run + ".json"
        report = json.loads(read(report_path), object_pairs_hook=pm.unique_keys)
        pm.require(state.get("last_run_id") == run and report.get("run_id") == run and report.get("status") == "success",
                   "Dreamer result is not the committed successful checkpoint; orphan proposals are not accepted")
        pm.require(report_path in source_paths, "accepted candidate must bind the committed Dreamer report")
        pm.require(pm.timestamp(report["finished_at"]) <= pm.timestamp(task["accepted"]["accepted_at"]), "task acceptance precedes Dreamer result")
        pm.require(all(state.get("source_hashes", {}).get(p) == dependencies[p] for p in source_paths if p.startswith("memory/episodes/")), "Dreamer source snapshot mismatch")
    for relative in ("AGENTS.md", "PROJECT.md", "docs/governance/promotion-rules.md", INDEX):
        read(relative)
    index_text = blobs[INDEX].decode("utf-8")
    routed = links(INDEX, index_text)
    changes = request["changes"]
    pm.require(isinstance(changes, list) and 0 < len(changes) <= 20, "provide 1..20 authored changes")
    proposed, edit_sources, titles = {}, {}, {}
    created_at = created_at or pm.now()
    stamp = pm.timestamp(created_at)
    pm.require(stamp <= datetime.now(timezone.utc) and stamp >= pm.timestamp(task["accepted"]["accepted_at"]), "proposal time precedes acceptance or is in the future")
    day = stamp.date().isoformat()
    history_label = f"\n\n## Refresh history ({day}; proposed, not accepted)\n\n"

    def route_guidance(relative):
        category = "/".join(PurePosixPath(relative).parts[:2])
        guide = category + "/README.md"
        pm.require(guide in routed, "category README is not routed through docs/00-index.md: " + guide)
        read(guide)
        if pm.confined(root, category + "/AGENTS.md").is_file():
            read(category + "/AGENTS.md")

    for change in changes:
        fields(change, {"path", "sha256", "title", "source_paths", "before", "after"})
        relative = path_name(change["path"])
        pm.require(relative in allowed and relative not in {INDEX} and relative not in proposed and relative.endswith(".md"), "target is outside configured authority or is duplicated: " + relative)
        route_guidance(relative)
        text(change["title"], 200)
        pm.require(not any(c in change["title"] for c in "\r\n[]"), "unsafe index label")
        refs = change["source_paths"]
        pm.require(isinstance(refs, list) and refs and all(isinstance(p, str) for p in refs) and set(refs) <= source_paths, "change needs selected source paths")
        before, after = change["before"], text(change["after"])
        pm.require(isinstance(before, str) and len(before) <= 4000, "invalid before text")
        raw = read(relative, absent=True)
        if raw is None:
            pm.require(change["sha256"] is None and before == "", "new page requires null baseline and empty before text")
            content = "# " + change["title"] + "\n\n" + after + "\n"
        else:
            pm.require(dependencies[relative] == digest(change["sha256"]), "stale target revision: " + relative)
            old = raw.decode("utf-8")
            pm.require(before and old.count(before) == 1, "replacement requires one exact old passage: " + relative)
            content = old.replace(before, after, 1)
        content += history_label + "Candidate " + json.dumps(request["candidate"]) + "; source paths: " + json.dumps(refs) + ".\n"
        content += "Prior passage (retained as history): " + json.dumps(before, ensure_ascii=True) + "\n"
        proposed[relative], edit_sources[relative], titles[relative] = content, refs, change["title"]
    if STATUS not in proposed:
        pm.require(STATUS in allowed, "status route is outside configured authority")
        route_guidance(STATUS)
        status = read(STATUS).decode("utf-8")
        proposed[STATUS] = status + f"\n\n## Proposed task update ({day}; owner review pending)\n\n" + json.dumps(request["title"], ensure_ascii=True) + "\n\n"
        proposed[STATUS] += "Accepted task candidate: " + json.dumps(request["candidate"]) + "; documentation remains proposed.\n"
        proposed[STATUS] += "Evidence classes and selected sources: " + json.dumps(sources, ensure_ascii=True, sort_keys=True) + "\n"
        edit_sources[STATUS] = sorted(source_paths)
    for relative, title in titles.items():
        category_readme = "/".join(PurePosixPath(relative).parts[:2]) + "/README.md"
        for route in (INDEX, category_readme):
            if route == relative:
                continue
            current = proposed.get(route, blobs[route].decode("utf-8"))
            if relative not in links(route, current):
                pm.require(route in allowed, "index route is outside configured authority: " + route)
                dest = PurePosixPath(relative).relative_to(PurePosixPath(route).parent).as_posix()
                proposed[route] = current + "\n- [" + title + "](" + quote(dest, safe="/") + ")\n"
                edit_sources[route] = sorted(source_paths)
    material_result = None
    if request["human_inventory"]:
        pm.require(policy["human_inventory"], "human-material inventory is not authorized by policy")
        index = "human-materials/README.md"
        material_text = read(index).decode("utf-8")
        inventory = hm.inventory(root)
        pm.require(all(e.startswith(("Missing row:", "Stale row:")) for e in inventory["errors"]), "unsafe or malformed material inventory; resolve links/invalid rows before proposing changes")
        actual = set(inventory["actual"])
        rows = {r["path"]: r for r in inventory["rows"]}
        missing, stale = sorted(actual - rows.keys()), sorted(rows.keys() - actual)
        material_result = {"scope": "selected human-materials tree only; coverage is not extraction", "actual": sorted(actual),
                           "missing_rows": missing, "stale_rows": stale, "reported_statuses": {p: r["status"] for p, r in rows.items()},
                           "extraction": "Not performed. Index statuses are reported assertions, not verified content coverage.",
                           "moves": "Not inferred. A missing and a stale name do not prove a move.",
                           "public_export_allowed": not actual and not rows and inventory.get("index_sha256") in hm.KNOWN_EMPTY_INDEX_SHA256}
        if missing or stale:
            lines = material_text.splitlines(keepends=True)
            retained = "".join(line for n, line in enumerate(lines, 1) if n not in {rows[p]["line"] for p in stale})
            additions = "".join("| [Unreviewed material](" + quote(p, safe="/") + ") | Filename only; content not reviewed. | unknown | unknown | unread | — |\n" for p in missing)
            separators = list(re.finditer(r"(?m)^\|[-: |]+\|[ \t]*\r?$", retained))
            pm.require(len(separators) == 1, "one unambiguous active material table is required")
            end = retained.find("\n", separators[0].end())
            end = len(retained) if end < 0 else end + 1
            retained = retained[:end] + ("\n" if end == len(retained) and not retained.endswith("\n") else "") + additions + retained[end:]
            if stale:
                retained += f"\n## Proposed inventory history ({day})\n\n" + "\n".join(
                    "> Prior index row (not active): " + json.dumps(rows[p]["text"], ensure_ascii=True) for p in stale) + "\n"
            proposed[index], edit_sources[index] = retained, []
    edits = [{"path": p, "before_sha256": dependencies[p], "after_sha256": pm.digest(value.encode("utf-8")),
              "proposed_text": value, "source_paths": edit_sources[p]} for p, value in sorted(proposed.items())]
    identity = {"request_sha256": pm.digest(ac.canonical(request).encode()), "dependencies": dependencies, "human_materials": material_result}
    ident = "refresh-" + pm.digest(ac.canonical(identity).encode())[:24]
    return {"version": 1, "id": ident, "status": "proposed", "created_at": created_at, "project_id": request["project_id"],
            "task_id": task["id"], "accepted_candidate": request["candidate"],
            "acceptance": {k: task["accepted"][k] for k in ("candidate", "by", "accepted_at", "evidence")},
            "owner_review_required": True, "request": request, **identity, "edits": edits,
            "limits": "Local snapshot reports acceptance; references are not independently authenticated. No semantic extraction, canonical writes or promotion. Recall has no cache to invalidate."}


def propose(root, request, write=False):
    root = Path(root).resolve()
    try:
        proposal = build(root, request)
        path = FOLDER + "/" + proposal["id"] + ".json"
        written = False
        if write:
            with pm.operation(root):
                pm.require(not pm.runtime(root, "lock.json").exists(), "Dreamer active; defer sidecar publication")
                verified = build(root, request, proposal["created_at"])
                pm.require(verified == proposal, "inputs changed during refresh preflight")
                target = pm.confined(root, path)
                for folder in target.parents:
                    if folder == root:
                        break
                    pm.require(not (folder / ".git").exists(), "private sidecar destination crosses a nested repository")
                def git(*args):
                    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=5)
                repository = git("rev-parse", "--is-inside-work-tree")
                pm.require(repository.returncode == 0 and repository.stdout.strip() == b"true",
                           "--write requires a Git worktree to verify sidecar privacy; preview remains read-only")
                tracked = git("ls-files", "-z", "--", path)
                pm.require(tracked.returncode == 0 and not tracked.stdout,
                           "sidecar destination is tracked or its index state is unavailable; refuse private publication")
                ignore = pm.confined(root, ".dreamdocs/.gitignore")
                if not ignore.exists():
                    from memory_capture import atomic_text
                    atomic_text(ignore, "*\n")
                pm.require(git("check-ignore", "-q", "--", path).returncode == 0,
                           "sidecar is not effectively excluded by Git; review ignore rules without tracking private content")
                if target.exists():
                    existing = pm.read_json(target)
                    pm.require(check(root, path)["ok"], "existing sidecar is stale or modified")
                    proposal = existing
                else:
                    pm.atomic(target, proposal)
                    pm.require(pm.read_json(target) == proposal, "sidecar readback mismatch")
                    written = True
        return {"exit": 0, "written": written, "path": path, "proposal": proposal}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as error:
        return {"exit": 2, "written": False, "findings": [{"code": "refresh_refused", "cause": type(error).__name__, "detail": str(error),
                                                           "next_action": "Reconcile the selected acceptance, policy and exact file revisions; no canonical files were changed."}]}


def check(root, relative):
    root = Path(root).resolve()
    changed = []
    try:
        path_name(relative)
        pm.require(PurePosixPath(relative).parent.as_posix() == FOLDER and relative.endswith(".json"), "select one private refresh sidecar")
        proposal = pm.read_json(pm.confined(root, relative))
        pm.require(proposal.get("status") == "proposed" and proposal.get("owner_review_required") is True and isinstance(proposal.get("dependencies"), dict), "invalid proposal sidecar")
        for path, expected in proposal["dependencies"].items():
            readable_input(path)
            if expected is not None:
                digest(expected)
            target = pm.confined(root, path)
            actual = pm.bounded_digest(target) if target.is_file() else None
            if actual != expected:
                changed.append(path)
        pm.require(not changed, "source/target/policy/acceptance revision changed")
        rebuilt = build(root, proposal["request"], proposal["created_at"])
        pm.require(proposal == rebuilt and relative == FOLDER + "/" + rebuilt["id"] + ".json", "proposal bytes or material inventory changed")
        return {"exit": 0, "ok": True, "changed_paths": [], "status": "proposed; owner review still required"}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        return {"exit": 2, "ok": False, "changed_paths": sorted(changed), "findings": [str(error)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("propose")
    create.add_argument("--request", required=True, help="Project-relative authored request JSON; no originals are read.")
    create.add_argument("--write", action="store_true", help="Write only the ignored private proposal sidecar.")
    verify = commands.add_parser("check")
    verify.add_argument("--proposal", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command == "propose":
            relative = path_name(args.request)
            pm.require(relative.startswith(".dreamdocs/"), "select a private request under .dreamdocs/; original materials are not request inputs")
            path = pm.confined(root, relative)
            pm.require(path.stat().st_size <= 131072, "request exceeds 128 KiB")
            request = pm.read_json(path)
            result = propose(root, request, args.write)
        else:
            result = check(root, args.proposal)
    except (OSError, ValueError) as error:
        result = {"exit": 2, "written": False, "findings": [type(error).__name__ + ": explicit input unavailable or invalid"]}
    print(json.dumps(result, sort_keys=True, indent=2))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
