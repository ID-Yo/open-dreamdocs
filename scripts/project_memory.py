#!/usr/bin/env python3
"""Validate a template and manage local Dreamer snapshots; never calls a model."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote, urlsplit
import uuid

sys.dont_write_bytecode = True
TYPES = {"episodes": "episodic", "facts": "semantic", "procedural": "procedural", "contradictions": "contradiction"}
STATUSES = {
    "episodic": {"active", "archived"},
    "semantic": {"proposed", "active", "disputed", "superseded", "archived"},
    "procedural": {"proposed", "active", "deprecated", "archived"},
    "contradiction": {"open", "resolved", "archived"},
}
KINDS = {"fact", "procedure", "contradiction", "duplicate", "archive"}
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")
# Managed template surface; everything else in an adopted project is out of scope.
MANAGED_DIRS = ("docs", "memory", "templates", "examples", "prompts", "scripts", "tests")
MANAGED_FILES = ("LICENSE", ".gitignore", "human-materials/README.md", "human-materials/.gitignore")
# Tool folders are skipped anywhere; generic names (build, dist, work) only at their known runtime path.
PRUNE = {".git", ".hg", ".svn", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", ".next"}
RUNTIME = {"memory/dreamer/work", "memory/automation/events", "memory/automation/pending"}


class MemoryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise MemoryError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    require(isinstance(value, str), "timestamp must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "timestamp must include a timezone")
    return parsed


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def confined(root, relative):
    path = root / relative
    require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, f"unsafe path: {relative}")
    require(path.resolve().is_relative_to(root), f"path escapes root: {relative}")
    for part in (path, *path.parents):
        if part == root:
            break
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()), f"linked path: {relative}")
    return path


def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    require(isinstance(value, dict), f"expected JSON object: {path.name}")
    return value


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def linked(path):
    info = os.lstat(path)
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT


def listing(root, folder):
    try:
        with os.scandir(folder) as entries:
            return sorted(entries, key=lambda entry: entry.name)
    except PermissionError as exc:
        raise MemoryError(f"permission denied in managed path: {folder.relative_to(root).as_posix() or '.'}") from exc


def walk(root, top, strict=False):
    """List a managed folder; skip tool/runtime trees and nested repositories before listing them (strict: fail instead)."""
    folders, files, stack = [], [], [top]
    while stack:
        folder = stack.pop()
        folders.append(folder)
        for entry in listing(root, folder):
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            skipped = entry.name in PRUNE or relative in RUNTIME
            if not skipped:
                require(not linked(path), f"linked path: {relative}")
                skipped = entry.is_dir(follow_symlinks=False) and ((path / ".git").exists() or (path / "pyvenv.cfg").exists())
            if skipped:
                require(not strict, f"unexpected dependency, runtime or repository folder in memory records: {relative}")
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
            elif entry.is_file(follow_symlinks=False):
                files.append(path)
    return sorted(folders), sorted(files)


def managed_files(root):
    """Explicit bounded manifest: root Markdown and package files, managed folders and the human-materials index."""
    files = []
    for entry in listing(root, root):
        if entry.name.endswith(".md") or entry.name in MANAGED_FILES:
            require(not linked(Path(entry.path)), f"linked path: {entry.name}")
            if entry.is_file(follow_symlinks=False):
                files.append(Path(entry.path))
    for name in MANAGED_DIRS:
        if confined(root, name).is_dir():
            files += walk(root, root / name)[1]
    files += [confined(root, name) for name in MANAGED_FILES if "/" in name and confined(root, name).is_file()]
    return sorted(files)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def metadata(text):
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    require(match is not None, "missing --- frontmatter")
    value = json.loads(match[1], object_pairs_hook=unique_keys)
    require(isinstance(value, dict), "frontmatter must be a JSON object (YAML 1.2 subset)")
    return value


def record_files(root, archive=True):
    categories = list(TYPES) + (["archive"] if archive else [])
    files = []
    for category in categories:
        folder = confined(root, f"memory/{category}")
        require(folder.is_dir(), f"missing memory/{category}")
        for path in walk(root, folder, strict=True)[1]:
            if path.suffix == ".md" and path.name != "README.md":
                files.append((category, path))
    return files


def validate_record(meta, category):
    required = {"id", "type", "status", "project", "scope", "created_at", "source"}
    require(required <= meta.keys(), f"missing fields: {sorted(required - meta.keys())}")
    require(isinstance(meta["id"], str) and IDENTIFIER.fullmatch(meta["id"]), "invalid id")
    require(meta["type"] in STATUSES, "unknown type")
    if category != "archive":
        require(meta["type"] == TYPES[category], "type does not match folder")
    require(meta["status"] in STATUSES[meta["type"]], "invalid status")
    if category == "archive":
        require(meta["status"] in {"archived", "superseded", "deprecated", "resolved"}, "archive contains live record")
    require(all(isinstance(meta[k], str) and meta[k].strip() for k in ("project", "scope")), "project/scope required")
    timestamp(meta["created_at"])
    require(isinstance(meta["source"], list) and meta["source"] and all(isinstance(v, str) and v.strip() for v in meta["source"]), "nonempty source list required")
    require(not re.search(r"<[A-Z_a-z][^>]*>", canonical(meta)), "unfilled metadata placeholder")
    if "pinned" in meta:
        require(type(meta["pinned"]) is bool, "pinned must be boolean")
    if meta["type"] in {"semantic", "procedural"}:
        require(isinstance(meta.get("owner"), str) and meta["owner"].strip(), "owner required")
        if meta.get("last_verified") is not None:
            timestamp(meta["last_verified"])
        if meta["status"] == "active":
            timestamp(meta.get("last_verified"))
            require(isinstance(meta.get("accepted_by"), str) and meta["accepted_by"].strip(), "active fact/method requires accepted_by")
    if meta.get("review_after") is not None:
        require(isinstance(meta["review_after"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["review_after"]), "review_after needs YYYY-MM-DD")
        datetime.strptime(meta["review_after"], "%Y-%m-%d")
    if meta["status"] == "superseded":
        require(isinstance(meta.get("superseded_by"), str) and meta["superseded_by"] != meta["id"], "superseded_by required")
    if meta["type"] == "procedural":
        require(type(meta.get("version")) is int and meta["version"] > 0, "positive version required")
        for key in ("success_count", "failure_count"):
            require(type(meta.get(key)) is int and meta[key] >= 0, f"nonnegative {key} required")


def records(root):
    items = []
    ids = set()
    for category, path in record_files(root):
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        try:
            meta = metadata(raw.decode("utf-8"))
            validate_record(meta, category)
            require(meta["id"] not in ids, f"duplicate id {meta['id']}")
            ids.add(meta["id"])
        except (ValueError, TypeError) as exc:
            raise MemoryError(f"{relative}: {exc}") from exc
        items.append({"path": relative, "sha256": digest(raw), "metadata": meta, "content": raw.decode("utf-8")})
    projects = {r["metadata"]["project"] for r in items}
    require(len(projects) <= 1, "records mix project identities")
    for item in items:
        meta = item["metadata"]
        refs = list(meta["source"])
        refs += ["id:" + meta[k] for k in ("supersedes", "superseded_by") if meta.get(k)]
        for ref in refs:
            require(ref.startswith(("id:", "file:", "https://", "ref:")), f"{meta['id']}: source needs id:, file:, https:// or ref:")
            if ref.startswith("id:"):
                require(ref[3:] in ids, f"{meta['id']}: unknown source ID {ref[3:]}")
            elif ref.startswith("file:"):
                require(confined(root, ref[5:]).is_file(), f"{meta['id']}: missing source file {ref[5:]}")
    return items


def settings(root):
    cfg = read_json(confined(root, "memory/config.json"))
    require(set(cfg) == {"version", "schedule", "review"} and cfg["version"] == 1, "unsupported config fields/version")
    schedule = cfg["schedule"]
    require(set(schedule) == {"frequency", "timezone", "local_time", "owner"} and schedule["frequency"] == "daily", "schedule must be daily with timezone/local_time/owner")
    for key in ("timezone", "owner"):
        require(schedule[key] is None or isinstance(schedule[key], str) and bool(schedule[key].strip()), f"invalid {key}")
    require(schedule["local_time"] is None or isinstance(schedule["local_time"], str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule["local_time"]), "local_time needs HH:MM")
    require(set(cfg["review"]) == {"episode_days"}, "unknown review field")
    days = cfg["review"]["episode_days"]
    require(days is None or type(days) is int and days > 0, "episode_days must be positive or null")
    return cfg


def validate_links(root):
    checked = 0
    selected = {path for path in managed_files(root) if path.suffix == ".md"}
    for path in sorted(selected):
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in re.findall(r"\]\(([^)]+)\)", text):
            url = urlsplit(target.strip("<>"))
            if url.scheme:
                continue
            destination = (path.parent / unquote(url.path)).resolve() if url.path else path
            require(destination.is_relative_to(root) and destination.exists(), f"broken/outside link: {path.relative_to(root)} -> {target}")
            if url.fragment and destination in selected:
                headings = re.findall(r"^#+\s+(.+)$", destination.read_text(encoding="utf-8"), re.M)
                anchors = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                require(unquote(url.fragment) in anchors, f"broken anchor: {target}")
            checked += 1
    return checked


def validate(root):
    cfg = settings(root)
    items = records(root)
    folders = [root / name for name in ("memory", "templates", "examples", "prompts", "scripts", "tests")]
    folders += [folder for name in ("docs", "memory") if confined(root, name).is_dir() for folder in walk(root, root / name)[0]]
    for folder in folders:
        if folder.is_dir():
            require((folder / "README.md").is_file() or folder == root / "docs", f"folder needs README: {folder.relative_to(root)}")
    state = read_json(confined(root, "memory/dreamer/state.json"), {})
    if state:
        timestamp(state.get("last_successful_at"))
        require(isinstance(state.get("source_hashes"), dict), "invalid checkpoint hashes")
        for key, value in state["source_hashes"].items():
            confined(root, key)
            require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value), "invalid checkpoint digest")
    return {"ok": True, "records": len(items), "links": validate_links(root), "scheduler_configured": all(cfg["schedule"][k] for k in ("timezone", "local_time", "owner"))}


def runtime(root, name):
    return confined(root, "memory/dreamer/" + name)


@contextlib.contextmanager
def operation(root):
    """Small process lock serializes runner commands, not unrelated source writers."""
    path = runtime(root, "command.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise MemoryError("another runner command is active; investigate command.lock before manual recovery") from exc
    try:
        os.write(fd, canonical({"owner_pid": os.getpid(), "acquired_at": now()}).encode())
    except BaseException:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def input_manifest(root, items):
    manifest = {r["path"]: r["sha256"] for r in items if not r["path"].startswith("memory/archive/")}
    manifest["memory/config.json"] = digest(confined(root, "memory/config.json").read_bytes())
    return manifest


def begin(root):
    with operation(root):
        require(not runtime(root, "lock.json").exists(), "run lock exists; finish/abort it or explicitly recover after confirming it stopped")
        cfg = settings(root)
        items = records(root)
        state = read_json(runtime(root, "state.json"), {})
        started = now()
        selected = []
        for item in items:
            if item["path"].startswith("memory/archive/"):
                continue
            meta = item["metadata"]
            changed = state.get("source_hashes", {}).get(item["path"]) != item["sha256"]
            due = meta.get("review_after") and meta["review_after"] <= started[:10] and meta["status"] == "active"
            days = cfg["review"]["episode_days"]
            old = meta["type"] == "episodic" and days is not None and not meta.get("pinned", False) and timestamp(meta["created_at"]) + timedelta(days=days) <= timestamp(started)
            if changed or due or old or meta["type"] == "contradiction" and meta["status"] == "open":
                selected.append(item)
        manifest = input_manifest(root, items)
        require(input_manifest(root, records(root)) == manifest, "sources changed while snapshot was being taken; retry")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S") + "-" + uuid.uuid4().hex[:8]
        snapshot = {"run_id": run_id, "started_at": started, "previous_checkpoint": state.get("last_successful_at"), "manifest": manifest, "records": selected}
        work = runtime(root, "work/" + run_id)
        atomic(work / "snapshot.json", snapshot)
        atomic(work / "result.json", {"run_id": run_id, "status": "pending", "summary": "", "reviewed_ids": [], "proposals": []})
        atomic(runtime(root, "lock.json"), {"run_id": run_id, "started_at": started, "snapshot_hash": digest((work / "snapshot.json").read_bytes())})
        return {"run_id": run_id, "records": len(selected), "snapshot": (work / "snapshot.json").relative_to(root).as_posix()}


def run_files(root, run_id):
    require(isinstance(run_id, str) and IDENTIFIER.fullmatch(run_id), "invalid run ID")
    lock = read_json(runtime(root, "lock.json"))
    require(lock.get("run_id") == run_id, "run does not own lock")
    work = runtime(root, "work/" + run_id)
    require(digest((work / "snapshot.json").read_bytes()) == lock.get("snapshot_hash"), "snapshot modified")
    snapshot = read_json(work / "snapshot.json")
    require(snapshot.get("run_id") == run_id, "snapshot run mismatch")
    return snapshot, work


def validate_result(snapshot, result):
    require(set(result) == {"run_id", "status", "summary", "reviewed_ids", "proposals"}, "unexpected/missing result fields")
    require(result["run_id"] == snapshot["run_id"], "result run mismatch")
    require(result["status"] in {"success", "partial", "failed"}, "set status to success, partial or failed after reviewing")
    require(isinstance(result["summary"], str) and result["summary"].strip(), "summary required")
    expected = {r["metadata"]["id"] for r in snapshot["records"]}
    reviewed = result["reviewed_ids"]
    require(isinstance(reviewed, list) and all(isinstance(i, str) for i in reviewed), "reviewed_ids must be strings")
    require(len(reviewed) == len(set(reviewed)) and set(reviewed) <= expected, "invalid/duplicate reviewed_ids")
    require(result["status"] != "success" or set(reviewed) == expected, "success must review every snapshot record")
    require(isinstance(result["proposals"], list), "proposals must be a list")
    for proposal in result["proposals"]:
        require(isinstance(proposal, dict) and set(proposal) == {"kind", "title", "source_ids", "body"}, "invalid proposal fields")
        require(proposal["kind"] in KINDS and all(isinstance(proposal[k], str) and proposal[k].strip() for k in ("title", "body")), "invalid kind/title/body")
        refs = proposal["source_ids"]
        require(isinstance(refs, list) and refs and all(isinstance(i, str) for i in refs) and set(refs) <= expected, "proposal needs snapshot source IDs")
        if proposal["kind"] == "archive":
            pinned = {r["metadata"]["id"] for r in snapshot["records"] if r["metadata"].get("pinned")}
            require(not set(refs) & pinned, "cannot propose automatic archival of pinned records")


def finish(root, run_id):
    with operation(root):
        snapshot, work = run_files(root, run_id)
        result = read_json(work / "result.json")
        validate_result(snapshot, result)
        require(input_manifest(root, records(root)) == snapshot["manifest"], "input changed during run; abort and retry without advancing checkpoint")
        proposal_ids = []
        if result["status"] == "success":
            for proposal in result["proposals"]:
                normalized = {**proposal, "source_ids": sorted(set(proposal["source_ids"]))}
                proposal_id = "proposal-" + digest(canonical(normalized).encode())[:24]
                proposal_ids.append(proposal_id)
                path = runtime(root, "proposals/" + proposal_id + ".json")
                if not path.exists():
                    atomic(path, {"id": proposal_id, "status": "proposed", "created_at": now(), "run_id": run_id, **normalized})
        report = {**result, "started_at": snapshot["started_at"], "finished_at": now(), "proposal_ids": proposal_ids}
        atomic(runtime(root, "reports/" + run_id + ".json"), report)
        if result["status"] == "success":
            require(input_manifest(root, records(root)) == snapshot["manifest"], "input changed before checkpoint; retry")
            atomic(runtime(root, "state.json"), {"version": 1, "last_successful_at": snapshot["started_at"], "completed_at": report["finished_at"], "last_run_id": run_id, "source_hashes": snapshot["manifest"]})
        runtime(root, "lock.json").unlink()
        return {"run_id": run_id, "status": result["status"], "checkpoint_advanced": result["status"] == "success", "proposals": len(proposal_ids)}


def abort(root, run_id):
    with operation(root):
        snapshot, _ = run_files(root, run_id)
        atomic(runtime(root, "reports/" + run_id + ".json"), {"run_id": run_id, "status": "failed", "summary": "Aborted; no checkpoint advancement", "started_at": snapshot["started_at"], "finished_at": now()})
        runtime(root, "lock.json").unlink()
        return {"run_id": run_id, "status": "failed", "checkpoint_advanced": False}


def recover(root, run_id, max_age_minutes, confirm_stopped):
    with operation(root):
        require(confirm_stopped and max_age_minutes > 0, "explicit stopped confirmation and positive age threshold required")
        require(IDENTIFIER.fullmatch(run_id), "invalid run ID")
        lock = read_json(runtime(root, "lock.json"))
        require(lock.get("run_id") == run_id, "run does not own lock")
        age = (timestamp(now()) - timestamp(lock["started_at"])).total_seconds() / 60
        require(age >= max_age_minutes, "lock is too recent for requested recovery threshold")
        atomic(runtime(root, "reports/" + run_id + "-recovered.json"), {"run_id": run_id, "status": "failed", "summary": "Explicitly recovered abandoned run", "finished_at": now()})
        runtime(root, "lock.json").unlink()
        return {"recovered": run_id, "checkpoint_advanced": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "begin", "finish", "abort", "recover"):
        sub = commands.add_parser(name)
        if name in {"finish", "abort", "recover"}:
            sub.add_argument("--run-id", required=True)
        if name == "recover":
            sub.add_argument("--max-age-minutes", required=True, type=int)
            sub.add_argument("--confirm-stopped", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.command in {"validate", "begin"}:
            result = globals()[args.command](root)
        elif args.command == "recover":
            result = recover(root, args.run_id, args.max_age_minutes, args.confirm_stopped)
        else:
            result = globals()[args.command](root, args.run_id)
        print(canonical(result), end="")
        return 0 if result.get("status", "success") == "success" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
