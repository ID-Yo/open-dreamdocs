"""Offline selected-package upgrade with explicit source pins, private staging and collision checks."""
from datetime import datetime, timezone
import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import uuid

import install
import project_memory as pm

UPSTREAM = "https://github.com/ID-Yo/open-dreamdocs"
RELEASE = "dreamdocs-release.json"
BACKUPS = ".dreamdocs/backups"
BASELINE = Path(__file__).parent / "releases/v1.4.0.json"
COMPATIBILITY_SCAFFOLD = {"memory/automation/README.md", "memory/automation/receipts/README.md"}
USER_GUIDANCE = {"scripts/README.md"}


def bundle_manifest(source, revision):
    """Publisher-side inventory only; its output becomes trusted only through separate review/pinning."""
    source = Path(source).resolve()
    pm.require(re.fullmatch(r"[a-f0-9]{40}", revision or ""), "supply the selected full revision")
    files = {p.relative_to(source).as_posix(): pm.digest(p.read_bytes()) for p in pm.managed_files(source)
             if package_asset(p.relative_to(source).as_posix())}
    return {"version": 1, "upstream": UPSTREAM, "revision": revision, "package_version": install.PACKAGE_VERSION,
            "memory_schema": 1, "files": dict(sorted(files.items()))}


def package_asset(relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        return False
    path = PurePosixPath(relative)
    if path.is_absolute() or any(p in {"..", "."} for p in path.parts) or path.as_posix() != relative:
        return False
    return (relative in COMPATIBILITY_SCAFFOLD
            or len(path.parts) > 1 and path.parts[0] == "scripts" and path.suffix in {".py", ".json", ".md"}
            or len(path.parts) > 1 and path.parts[0] == "adapters" and path.suffix in {".py", ".md"}
            or len(path.parts) == 2 and path.parts[0] == "templates" and path.name.endswith(".schema.json"))


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_bytes(root, relative):
    path = pm.confined(root, relative)
    if path.exists() and not path.is_file():
        raise ValueError(f"not a file: {relative}")
    return path.read_bytes() if path.is_file() else None


def hash_bytes(value):
    return pm.digest(value) if value is not None else None


def payload_path(backup, label, path, journal):
    suffix = ".bin" if journal.get("payload_encoding") == "binary-v1" else ""
    return f"{backup}/{label}/{path}{suffix}"


def backup_privacy(root, backup, paths, initialize=False):
    """Verify exact private destinations before publication; plain copies remain supported."""
    ignore = pm.confined(root, ".dreamdocs/.gitignore")
    if initialize and not ignore.exists():
        atomic_bytes(ignore, b"/backups/\n")
    for folder in pm.confined(root, backup).parents:
        if folder == root:
            break
        pm.require(not (folder / ".git").exists(), "private backup crosses a nested repository")
    def git(*args, data=None):
        return subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True, timeout=5)
    try:
        repo = git("rev-parse", "--is-inside-work-tree")
        in_git = repo.returncode == 0 and repo.stdout.strip() == b"true"
    except FileNotFoundError:
        in_git = False
    if not in_git:
        pm.require(not any((p / ".git").exists() for p in (root, *root.parents)), "Git backup privacy could not be verified; restore Git access and retry")
        if initialize:
            own_ignore = pm.confined(root, backup + "/.gitignore")
            pm.require(not own_ignore.exists() or own_ignore.read_bytes() == b"*\n", "existing private backup ignore file changed; preserve and review it")
            if not own_ignore.exists():
                atomic_bytes(own_ignore, b"*\n")
        return "non-Git local backup is self-ignoring; review private paths before future Git adoption/export"
    tracked = git("ls-files", "-z", "--", backup)
    pm.require(tracked.returncode == 0 and not tracked.stdout, "private backup destinations are tracked or index state is unavailable; explicitly untrack/review before retry")
    if not ignore.exists() and not initialize:
        return "a missing local backup ignore file will be created and verified under the writer lock"
    requested = set(paths)
    for path in requested:
        pm.confined(root, path)
    checked = git("check-ignore", "-z", "--stdin", data=b"\0".join(p.encode("utf-8") for p in sorted(requested)) + b"\0")
    actual = {p.decode("utf-8") for p in checked.stdout.split(b"\0") if p}
    pm.require(checked.returncode == 0 and actual == requested,
               "private backup paths are not effectively Git-excluded; review .dreamdocs ignore negations before retry (owner rules preserved)")
    return "exact backup/journal paths are untracked and effectively Git-excluded; later rule changes/force-add remain owner-controlled"


def selected_source(source, expected_manifest, revision):
    source = Path(source).resolve()
    raw = pm.confined(source, RELEASE).read_bytes()
    pm.require(re.fullmatch(r"[a-f0-9]{64}", expected_manifest or "") and pm.digest(raw) == expected_manifest,
               "selected manifest does not match the independently reviewed SHA-256 pin")
    data = json.loads(raw)
    pm.require(isinstance(data, dict) and set(data) == {"version", "upstream", "revision", "package_version", "memory_schema", "files"}, "invalid release manifest fields")
    pm.require(type(data["version"]) is int and data["version"] == 1 and type(data["memory_schema"]) is int and data["memory_schema"] == 1, "unsupported release/record schema; no speculative migration")
    pm.require(data["upstream"] == UPSTREAM and re.fullmatch(r"[a-f0-9]{40}", revision or "") and data["revision"] == revision,
               "selected source identity differs from the reviewed upstream/revision")
    pm.require(isinstance(data["package_version"], str) and bool(data["package_version"]), "missing package version")
    pm.require(isinstance(data["files"], dict) and all(package_asset(p) and isinstance(h, str) and re.fullmatch(r"[a-f0-9]{64}", h) for p, h in data["files"].items()), "invalid package-owned file map")
    pm.require({"scripts/dreamdocs.py", "scripts/install.py", "scripts/project_memory.py", install.BLOCK_FILE, *COMPATIBILITY_SCAFFOLD} <= data["files"].keys(), "selected package is incomplete (required automation scaffolding missing)")
    files = {p: pm.confined(source, p).read_bytes() for p in data["files"]}
    pm.require(all(pm.digest(raw) == data["files"][p] for p, raw in files.items()), "selected package file checksum mismatch")
    tree = ast.parse(files["scripts/install.py"].decode("utf-8"))
    declared = [node.value.value for node in tree.body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(target, ast.Name) and target.id == "PACKAGE_VERSION" for target in node.targets)]
    pm.require(declared == [data["package_version"]], "release version differs from package code declaration")
    return data, files


def writable_state(root):
    for relative in ("memory/dreamer/command.lock", "memory/dreamer/lock.json"):
        pm.require(not pm.confined(root, relative).exists(), f"active or unresolved writer: {relative}; no automatic lock removal")
    pm.settings(root)  # v1 -> v1 only; reject unsupported schemas before staging or writes
    pm.records(root)
    backups = pm.confined(root, BACKUPS)
    if backups.is_dir():
        for path in backups.glob("*/journal.json"):
            journal = pm.read_json(pm.confined(root, path.relative_to(root).as_posix()))
            pm.require(journal.get("state") in {"committed", "rolled_back"},
                       f"unfinished transaction: {path.parent.name}; inspect and rollback it before another update")


def baseline(root, installed, from_version):
    if installed:
        pm.require(installed.get("version") == 1 and isinstance(installed.get("package_files"), dict), "unsupported install manifest")
        files = installed["package_files"]
        # Setup in 1.5.0-rc.1/rc.2 also recorded project-owned files under scripts/ and adapters/
        # (for example scripts/build.ps1). They are user data, never package assets.
        files = {p: h for p, h in files.items() if package_asset(p)}
        pm.require(all(isinstance(h, str) and re.fullmatch(r"[a-f0-9]{64}", h) for h in files.values()), "invalid installed package baseline")
        return files, installed["package"].get("version", "unknown")
    pm.require(from_version == "v1.4.0", "unknown installed base: select --from-version v1.4.0 only for a known v1.4.0 adoption")
    data = pm.read_json(BASELINE)
    pm.require(data["revision"] == "26c7aff57be6ffb4ccd6287c979e3782a0a19b2a" and data["upstream"] == UPSTREAM, "invalid bundled legacy baseline")
    pm.require(any(read_bytes(root, p) is not None for p in data["files"]), "no known legacy executable assets found; unknown base")
    return data["files"], "v1.4.0"


def update(root, source, expected_manifest, revision, apply=False, from_version=None, clients=None):
    root = Path(root).resolve()
    report = {"exit": 5, "applied": False, "actions": [], "conflicts": [], "state": "blocked"}
    try:
        release, incoming = selected_source(source, expected_manifest, revision)
        writable_state(root)
        old_manifest = read_bytes(root, install.MANIFEST)
        installed = json.loads(old_manifest) if old_manifest is not None else {}
        old_files, old_version = baseline(root, installed, from_version)
        writes, before = {}, {}

        def action(path, data, owned=True):
            current = read_bytes(root, path)
            before[path] = current
            if current == data:
                mode = "unchanged"
            elif owned and current is not None and hash_bytes(current) != old_files.get(path):
                mode = "conflict"
            elif owned and current is None and path in old_files:
                mode = "conflict"  # a local deletion is also an edit
            else:
                mode = "delete" if data is None else "create" if current is None else "update"
                writes[path] = data
            report["actions"].append({"path": path, "action": mode, "baseline_sha256": old_files.get(path),
                                      "local_sha256": hash_bytes(current), "incoming_sha256": hash_bytes(data)})
            if mode == "conflict":
                report["conflicts"].append(f"Locally edited or unknown-base package asset: {path}. Preserve/merge it explicitly, then retry.")

        package_files = {p: sha for p, sha in release["files"].items() if p not in COMPATIBILITY_SCAFFOLD | USER_GUIDANCE}
        for path in sorted(set(old_files) | set(incoming)):
            if path in COMPATIBILITY_SCAFFOLD | USER_GUIDANCE and read_bytes(root, path) is not None:
                # Existing runtime notes and script guidance are user-owned. Do not install links
                # to new canonical pages that a legacy project deliberately has not adopted.
                before[path] = read_bytes(root, path)
                report["actions"].append({"path": path, "action": "retained_user_data"})
            elif path not in incoming and read_bytes(root, path) is not None:
                # The recorded baseline can include project-owned files; an upgrade never deletes them.
                before[path] = read_bytes(root, path)
                report["actions"].append({"path": path, "action": "retained_not_in_package"})
            else:
                action(path, incoming.get(path), owned=path not in COMPATIBILITY_SCAFFOLD)
        for client, record in installed.get("clients", {}).items():
            pm.require(client in install.CLIENTS, "unknown installed client")
            path = install.CLIENTS[client]["hook_file"]
            pm.require(hash_bytes(read_bytes(root, path)) == record.get("written_sha256"), f"locally changed hook config: {path}; inspect and merge explicitly")
        for path, record in installed.get("merged", {}).items():
            pm.require(path in {"AGENTS.md", "CLAUDE.md"}, "unknown merged instruction path")
            text = install.read(root, path)
            pm.require(text is not None and install.block_digest(text) == record.get("sha256"), f"locally changed instruction block: {path}")
        chosen = tuple(clients or installed.get("clients", {}) or ("codex",))
        pm.require(set(chosen) <= set(install.CLIENTS), "unknown client")
        setup_report, setup_writes, conflicts = install.plan(root, clients=chosen,
            block_text=incoming[install.BLOCK_FILE].decode("utf-8"), package_files=package_files)
        report["conflicts"] += [message for _, message in conflicts]
        manifest = json.loads(setup_writes[install.MANIFEST])
        manifest["package"] = {"version": release["package_version"], "revision": revision, "upstream": UPSTREAM, "manifest_sha256": expected_manifest}
        setup_writes[install.MANIFEST] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        # Private backup protection is additive, never replace the user's ignore rules.
        setup_writes.pop(".dreamdocs/.gitignore", None)
        for path, text in setup_writes.items():
            pm.require(path in {install.MANIFEST, install.BINDING, "AGENTS.md", "CLAUDE.md"}
                       or path in {s[k] for s in install.CLIENTS.values() for k in ("hook_file", "ignore")}
                       or path in {f"{install.BACKUP}/{s['hook_file']}" for s in install.CLIENTS.values()}, "unexpected setup write path")
            action(path, text.encode("utf-8"), owned=False)
        if installed.get("package", {}).get("manifest_sha256") == expected_manifest and not any(a["action"] not in {"unchanged", "retained_user_data"} for a in report["actions"] if a["path"] != install.MANIFEST):
            report.update(exit=0, state="unchanged", actions=[a for a in report["actions"] if a["path"] != install.MANIFEST])
            return report
        report.update(source={"upstream": UPSTREAM, "revision": revision, "manifest_sha256": expected_manifest}, from_version=old_version,
                      to_version=release["package_version"], next_steps=setup_report["next_steps"], warnings=setup_report["warnings"],
                      compatibility="Client trust and real fresh-session save/recall probes required after apply; configuration is not runtime proof.")
        if report["conflicts"]:
            return report
        required = sum(len(data or b"") + len(before[p] or b"") for p, data in writes.items()) * 2 + 1048576
        pm.require(shutil.disk_usage(root).free >= required, "insufficient free space for staged files and backups")
        backup = f"{BACKUPS}/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
        private_paths = [backup + "/journal.json"] + [payload_path(backup, label, path, {"payload_encoding": "binary-v1"})
            for path, data in writes.items() for label, value in (("before", before[path]), ("after", data)) if value is not None]
        report["backup_privacy"] = backup_privacy(root, backup, private_paths)
        report.update(exit=0, state="planned; nothing written")
        if not apply:
            return report
        with pm.operation(root):
            pm.require(not pm.runtime(root, "lock.json").exists(), "Dreamer run became active; retry after it stops")
            for path in before:
                pm.require(read_bytes(root, path) == before[path], f"target changed during preflight: {path}")
            report["backup_privacy"] = backup_privacy(root, backup, private_paths, initialize=True)
            journal = {"version": 1, "payload_encoding": "binary-v1", "state": "staging", "source": report["source"], "from_version": old_version,
                       "to_version": release["package_version"], "created_at": pm.now(), "files": []}
            journal_path = pm.confined(root, backup + "/journal.json")
            report["backup"] = backup
            try:
                for path, data in writes.items():
                    item = {"path": path, "before_sha256": hash_bytes(before[path]), "after_sha256": hash_bytes(data)}
                    journal["files"].append(item)
                    for label, value in (("before", before[path]), ("after", data)):
                        if value is not None:
                            atomic_bytes(pm.confined(root, payload_path(backup, label, path, journal)), value)
                journal["state"] = "prepared"
                pm.atomic(journal_path, journal)
                # Claim the new installed version only after every other write and validation succeeded.
                ordered = sorted(p for p in writes if p != install.MANIFEST) + [install.MANIFEST]
                for path in ordered:
                    if path == install.MANIFEST:
                        pm.validate_runtime(root)  # documentation style rules never block a working upgrade
                        pm.require(all(hash_bytes(read_bytes(root, p)) == sha for p, sha in package_files.items()), "staged package readback mismatch")
                    pm.require(read_bytes(root, path) == before[path], f"target edited during update: {path}")
                    target = pm.confined(root, path)
                    data = writes[path]
                    if data is None:
                        target.unlink()
                    else:
                        atomic_bytes(target, data)
                    pm.require(read_bytes(root, path) == data, f"write readback mismatch: {path}")
                journal["state"] = "committed"
                pm.atomic(journal_path, journal)
                report.update(applied=True, state="updated; client trust and lifecycle probes pending")
            except (OSError, ValueError) as error:
                journal["state"] = "interrupted"
                try:
                    pm.atomic(journal_path, journal)
                except OSError:
                    pass  # staged bytes remain; report exact recovery location even when disk is unavailable
                report.update(exit=5, state="interrupted; inspect private backup and rollback before retrying")
                report["conflicts"].append(type(error).__name__ + ": " + str(error))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as error:
        report["exit"] = 5
        report["conflicts"].append(type(error).__name__ + ": " + str(error))
    return report


def rollback(root, backup, apply=False):
    """Restore only transaction-owned paths whose bytes still match before/after journal hashes."""
    root = Path(root).resolve()
    report = {"exit": 5, "applied": False, "actions": [], "conflicts": []}
    try:
        parts = PurePosixPath(backup).parts
        pm.require(len(parts) == 3 and parts[:2] == (".dreamdocs", "backups") and "\\" not in backup,
                   "select one exact project-private backup directory")
        journal_path = pm.confined(root, backup + "/journal.json")
        raw_journal = journal_path.read_bytes()
        journal = json.loads(raw_journal)
        pm.require(journal.get("version") == 1 and journal.get("state") in {"prepared", "interrupted", "committed", "rolling_back", "rolled_back"}, "invalid or incomplete transaction journal")
        for name in ("command.lock", "lock.json"):
            pm.require(not pm.runtime(root, name).exists(), "writer active or unresolved; rollback deferred")
        pm.settings(root)
        pm.records(root)
        writes, seen, before = {}, set(), {}
        private_paths = [backup + "/journal.json"]
        allowed_setup = {install.MANIFEST, install.BINDING, "AGENTS.md", "CLAUDE.md"}
        allowed_setup |= {s[k] for s in install.CLIENTS.values() for k in ("hook_file", "ignore")}
        allowed_setup |= {f"{install.BACKUP}/{s['hook_file']}" for s in install.CLIENTS.values()}
        pm.require(isinstance(journal.get("files"), list), "invalid rollback file map")
        for record in journal["files"]:
            path = record["path"]
            pm.require(path not in seen and (package_asset(path) or path in allowed_setup), "invalid/duplicate rollback target")
            seen.add(path)
            current = read_bytes(root, path)
            before[path] = current
            desired = None
            for label in ("before", "after"):
                expected = record[label + "_sha256"]
                pm.require(expected is None or isinstance(expected, str) and re.fullmatch(r"[a-f0-9]{64}", expected), "invalid rollback checksum")
                value = read_bytes(root, payload_path(backup, label, path, journal))
                if expected is not None:
                    private_paths.append(payload_path(backup, label, path, journal))
                pm.require(hash_bytes(value) == expected, "backup checksum mismatch: " + path)
                if label == "before":
                    desired = value
            sha = hash_bytes(current)
            if path in COMPATIBILITY_SCAFFOLD and record["before_sha256"] is None and current is not None:
                # Retained post-upgrade memory needs its parents' READMEs even under the old validator.
                # Any owner edits become retained user data, never silently overwritten/deleted.
                mode = "retained_compatibility_scaffold"
            elif sha == record["before_sha256"]:
                mode = "unchanged"
            elif sha == record["after_sha256"]:
                mode = "delete" if desired is None else "restore"
                writes[path] = desired
            else:
                mode = "conflict"
                report["conflicts"].append("Changed since update; preserve/merge explicitly before rollback: " + path)
            report["actions"].append({"path": path, "action": mode})
        legacy = journal.get("from_version") == "v1.4.0"
        report["compatibility"] = ("Legacy v1.4.0 has no automatic lifecycle adapters; automatic save/recall unavailable after rollback. Memory is preserved."
                                   if legacy else "Restored automation package requires real client probes and renewed hook trust where applicable; fixture save/recall is not real client acceptance.")
        report["backup"] = backup
        report["backup_privacy"] = backup_privacy(root, backup, private_paths)
        if report["conflicts"]:
            return report
        if journal["state"] == "rolled_back":
            report.update(exit=0, state="already rolled back")
            return report
        report.update(exit=0, state="planned; nothing written")
        if not apply:
            return report
        with pm.operation(root):
            pm.require(not pm.runtime(root, "lock.json").exists(), "Dreamer became active")
            pm.require(journal_path.read_bytes() == raw_journal, "journal changed during rollback planning")
            pm.require(all(read_bytes(root, p) == data for p, data in before.items()), "target changed during rollback planning")
            report["backup_privacy"] = backup_privacy(root, backup, private_paths, initialize=True)
            journal["state"] = "rolling_back"
            pm.atomic(journal_path, journal)
            try:
                for path in sorted(p for p in writes if p != install.MANIFEST) + ([install.MANIFEST] if install.MANIFEST in writes else []):
                    pm.require(read_bytes(root, path) == before[path], "target changed during rollback: " + path)
                    data, target = writes[path], pm.confined(root, path)
                    if data is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_bytes(target, data)
                    pm.require(read_bytes(root, path) == data, "rollback readback mismatch: " + path)
                pm.validate_runtime(root)
                journal["state"] = "rolled_back"
                journal["rolled_back_at"] = pm.now()
                pm.atomic(journal_path, journal)
                report.update(applied=True, state="rolled back; memory retained; review compatibility and trust")
            except (OSError, ValueError) as error:
                report.update(exit=5, state="rollback interrupted; retry the same backup after resolving the cause")
                report["conflicts"].append(type(error).__name__ + ": " + str(error))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as error:
        report["exit"] = 5
        report["conflicts"].append(type(error).__name__ + ": " + str(error))
    return report
