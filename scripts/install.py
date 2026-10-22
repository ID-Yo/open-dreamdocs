#!/usr/bin/env python3
"""Project setup and removal for Dreamdocs automation (issue #15).

Dry run by default. --apply writes only project files: the binding, Dreamdocs entries merged into
.codex/hooks.json, the instruction block in AGENTS.md and a versioned install manifest. It never edits
user-level client config, never bypasses hook trust, never runs a client and never touches memory records.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_contract as ac
import memory_capture as mc
import project_memory as pm

PACKAGE_VERSION = "unreleased"
BINDING, MANIFEST, HOOKS, AGENTS = "memory/automation.json", "memory/automation/install.json", ".codex/hooks.json", "AGENTS.md"
HOOK_SCRIPT, BLOCK_FILE = "adapters/codex/hook.py", "adapters/outcome-block.md"
LOCAL, BACKUP = ".dreamdocs", ".dreamdocs/backup"  # machine-local state; .dreamdocs/.gitignore ignores the folder
EVENTS = ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd")
TIMEOUTS = {"SessionStart": 15, "UserPromptSubmit": 10, "Stop": 30, "SessionEnd": 3}
BLOCK_START, BLOCK_END = "<!-- dreamdocs:automation:start -->", "<!-- dreamdocs:automation:end -->"
MEMORY_POLICY = ("Memory stays in this project folder: episodes and receipts are ordinary files you may commit; "
                 "memory/automation/events and pending are local and Git-ignored. Nothing is sent to a cloud service "
                 "and no model is called by the hooks.")
TRUST_STEP = ("Open Codex in this project, run /hooks, review the four Dreamdocs hooks (SessionStart, UserPromptSubmit, "
              "Stop, SessionEnd) and trust them; trust the project's .codex folder if asked. Do not use "
              "--dangerously-bypass-hook-trust. Changed hooks need review again after every setup or upgrade.")
REMOVAL = "python -B scripts/dreamdocs.py uninstall --apply removes the hooks, instruction block, binding and manifest; memory and docs stay."


def codex_version():
    """Installed Codex CLI version from its npm package, without running the client; None when not found."""
    found = shutil.which("codex")
    if not found:
        return None
    package = Path(found).resolve().parent / "node_modules" / "@openai" / "codex" / "package.json"
    try:
        return json.loads(package.read_text(encoding="utf-8")).get("version") or "unknown"
    except (OSError, ValueError):
        return "unknown"


def short_path(text):
    if os.name != "nt":
        return None
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetShortPathNameW(text, buffer, len(buffer))
    return buffer.value if 0 < length < len(buffer) else None


def shell_path(path):
    """A path usable unquoted by both cmd and PowerShell when possible; otherwise quoted with a warning."""
    text = str(path)
    if " " not in text:
        return text, None
    short = short_path(text)
    if short and " " not in short:
        return short, None
    return f'"{text}"', f"path with spaces is quoted and untested in the Codex hook shell: {text}"


def is_ours(handler):
    command = str(handler.get("command", "")).replace("\\", "/") if isinstance(handler, dict) else ""
    return command.endswith("/" + HOOK_SCRIPT) or command.endswith("/" + HOOK_SCRIPT + '"')


def without_ours(data):
    """Remove Dreamdocs handlers; keep every other key, group and handler exactly."""
    hooks = data.get("hooks", {})
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        groups = []
        for group in hooks[event]:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list) and any(is_ours(h) for h in group["hooks"]):
                group = {**group, "hooks": [h for h in group["hooks"] if not is_ours(h)]}
                if not group["hooks"]:
                    continue
            groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    return data


def merged_hooks(existing, command):
    data = without_ours(json.loads(json.dumps(existing))) if existing is not None else {}
    hooks = data.setdefault("hooks", {})
    for event in EVENTS:
        hooks.setdefault(event, []).append({"hooks": [{"type": "command", "command": command, "timeout": TIMEOUTS[event],
                                                         "statusMessage": "Dreamdocs memory"}]})
    return data


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def block_span(text):
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if start < 0 or end < start:
        return None
    stop = text.find("\n", end)
    return start, (stop + 1 if stop >= 0 else len(text))


def with_block(text, block, prefix=None):
    """Insert or replace the block in the file's own newline style. Returns (text, prefix inserted before it)."""
    if not text:
        return block, ""
    block = block.replace("\r\n", "\n").replace("\n", newline_of(text))
    span = block_span(text)
    if span:
        return text[:span[0]] + block + text[span[1]:], prefix or ""
    sep = newline_of(text)
    prefix = ("" if text.endswith(("\n", "\r")) else sep) + sep
    return text + prefix + block, prefix


def without_block(text, prefix):
    """Remove the block; when it is still at the end, also remove exactly the prefix setup inserted."""
    span = block_span(text)
    if span is None:
        return text
    head, tail = text[:span[0]], text[span[1]:]
    if not tail and prefix and head.endswith(prefix):
        head = head[:-len(prefix)]
    return head + tail


def read(root, relative):
    """Exact file text: newlines are never translated, so user files keep their bytes."""
    path = pm.confined(root, relative)
    return path.read_bytes().decode("utf-8") if path.is_file() else None


def project_identity(root, requested, binding):
    if binding is not None:
        return binding["project_id"]
    if requested:
        return requested
    try:
        projects = {item["metadata"]["project"] for item in pm.records(root)}
    except (OSError, ValueError):
        projects = set()
    if len(projects) == 1:
        return projects.pop()
    return re.sub(r"[^a-z0-9._-]+", "-", root.name.lower()).strip("-._") or "project"


def plan(root, project_id=None):
    """Compute every write without performing it. Returns (report, writes)."""
    root = Path(root).resolve()
    conflicts, warnings, writes, actions = [], [], {}, []
    version = codex_version()
    if version is None:
        conflicts.append(("client", "Install Codex CLI (npm install -g @openai/codex), then run setup again."))
    binding = None
    text = read(root, BINDING)
    if text is not None:
        try:
            binding = json.loads(text)
            ac.validate_binding(binding)
        except ValueError:
            conflicts.append((BINDING, f"Fix or remove {BINDING}; it is not a valid version 1 binding."))
            binding = None
        else:
            if project_id and project_id != binding["project_id"]:
                conflicts.append((BINDING, f"{BINDING} belongs to project '{binding['project_id']}'; rerun without --project-id or remove the binding."))
    identity = project_identity(root, project_id, binding)
    adapters = sorted(set(binding["adapters"] if binding else []) | {"codex"})
    writes[BINDING] = json.dumps({"version": 1, "project_id": identity, "adapters": adapters}, indent=2) + "\n"
    python, warn_python = shell_path(Path(sys.executable).resolve())
    script, warn_script = shell_path(root / HOOK_SCRIPT)
    warnings += [w for w in (warn_python, warn_script) if w]
    command = f"{python} -B {script}"
    existing = read(root, HOOKS)
    try:
        current = json.loads(existing) if existing is not None else None
        pm.require(current is None or isinstance(current, dict) and isinstance(current.get("hooks", {}), dict), "not a hooks object")
        writes[HOOKS] = json.dumps(merged_hooks(current, command), indent=2) + "\n"
    except ValueError:
        conflicts.append((HOOKS, f"Fix {HOOKS}: it is not a valid Codex hooks JSON object. Setup never overwrites it."))
    toml = read(root, ".codex/config.toml")
    if toml is not None and re.search(r"^\s*\[\[?hooks", toml, re.M):
        warnings.append(".codex/config.toml also defines hooks; Codex loads both and warns at startup.")
    block = read(root, BLOCK_FILE)
    old = read(root, MANIFEST)
    previous = json.loads(old) if old else {}
    writes[AGENTS], prefix = with_block(read(root, AGENTS), block, previous.get("merged", {}).get(AGENTS, {}).get("prefix"))
    if existing is not None and HOOKS in writes and HOOKS not in previous.get("created", []) and read(root, f"{BACKUP}/{HOOKS}") is None:
        writes[f"{BACKUP}/{HOOKS}"], writes[f"{LOCAL}/.gitignore"] = existing, "*\n"  # original bytes for uninstall
    package = sorted(path.relative_to(root).as_posix() for path in pm.managed_files(root)
                     if path.relative_to(root).parts[0] in {"scripts", "adapters"} or path.name.endswith(".schema.json"))
    created = sorted(set(previous.get("created", [])) | {p for p in (HOOKS, AGENTS) if read(root, p) is None})
    manifest = {"version": 1, "package": {"version": PACKAGE_VERSION}, "project_id": identity,
                "installed_at": previous.get("installed_at") or pm.now(),
                "python": platform.python_version(),
                "clients": {"codex": {"version": version, "hook_file": HOOKS, "events": list(EVENTS),
                                      "hook_sha256": pm.digest(command.encode()), "trust": "pending", "probe": "pending",
                                      "written_sha256": pm.digest(writes[HOOKS].encode()) if HOOKS in writes else None}},
                "package_files": {p: pm.digest((root / p).read_bytes()) for p in package},
                "merged": {AGENTS: {"block": "dreamdocs:automation", "sha256": pm.digest(block.replace("\r\n", "\n").encode()), "prefix": prefix}},
                "created": created,
                "user_owned": ["docs/", "memory/ records and receipts", "human-materials/", "PROJECT.md"],
                "local_only": ["memory/automation/events/", "memory/automation/pending/", "absolute paths in " + HOOKS]}
    if previous and {k: v for k, v in previous.items() if k != "installed_at"} == {k: v for k, v in manifest.items() if k != "installed_at"}:
        manifest = previous
    writes[MANIFEST] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    for path in (BINDING, HOOKS, AGENTS, MANIFEST, f"{BACKUP}/{HOOKS}", f"{LOCAL}/.gitignore"):
        if path in writes:
            before = read(root, path)
            actions.append({"path": path, "action": "create" if before is None else "unchanged" if before == writes[path] else "update"})
    report = {"root": str(root), "python": sys.executable, "hook_command": command, "project_id": identity,
              "clients": {"codex": {"version": version, "support": ac.SUPPORT["codex"]["state"]}},
              "actions": actions, "warnings": warnings, "memory_policy": MEMORY_POLICY, "removal": REMOVAL,
              "conflicts": [c for _, c in conflicts], "next_steps": [c for _, c in conflicts] or [TRUST_STEP]}
    return report, writes, conflicts


def setup(root, apply=False, project_id=None):
    root = Path(root).resolve()
    report, writes, conflicts = plan(root, project_id)
    exit_code = 5 if any(kind != "client" for kind, _ in conflicts) else 4 if conflicts else 0
    report.update(exit=exit_code, applied=False, state="needs action" if conflicts else "planned; nothing written (use --apply)")
    if not apply or conflicts:
        return report
    for action in report["actions"]:
        if action["action"] != "unchanged":
            mc.atomic_text(pm.confined(root, action["path"]), writes[action["path"]])
    report.update(applied=True, state="installed; Codex hook trust pending; probe pending")
    return report


def uninstall(root, apply=False):
    root = Path(root).resolve()
    manifest = json.loads(read(root, MANIFEST) or "{}")
    created, actions, notes = set(manifest.get("created", [])), [], []
    hooks = read(root, HOOKS)
    backup = read(root, f"{BACKUP}/{HOOKS}")
    if hooks is not None:
        unchanged = pm.digest(hooks.encode()) == manifest.get("clients", {}).get("codex", {}).get("written_sha256")
        data = without_ours(json.loads(hooks))
        if not data and HOOKS in created:
            actions.append((HOOKS, "delete", None))
        elif unchanged and backup is not None:
            actions.append((HOOKS, "restore", backup))
        else:
            actions.append((HOOKS, "update", json.dumps(data, indent=2, ensure_ascii=False) + "\n"))
            notes.append(f"{HOOKS} changed after setup: Dreamdocs entries removed, other content kept, formatting not preserved")
    if backup is not None:
        actions += [(f"{BACKUP}/{HOOKS}", "delete", None), (f"{LOCAL}/.gitignore", "delete", None)]
    agents = read(root, AGENTS)
    if agents is not None and BLOCK_START in agents:
        remaining = without_block(agents, manifest.get("merged", {}).get(AGENTS, {}).get("prefix", ""))
        gone = not remaining.strip() and AGENTS in created
        actions.append((AGENTS, "delete" if gone else "update", None if gone else remaining))
    for path in (BINDING, MANIFEST):
        if read(root, path) is not None:
            actions.append((path, "delete", None))
    if apply:
        for path, action, text in actions:
            target = pm.confined(root, path)
            if action == "delete":
                target.unlink(missing_ok=True)
            elif text != read(root, path):
                mc.atomic_text(target, text)
        for folder in (BACKUP + "/.codex", BACKUP, LOCAL, ".codex"):
            path = pm.confined(root, folder)
            if path.is_dir() and not any(path.iterdir()) and (folder != ".codex" or HOOKS in created):
                path.rmdir()
    return {"exit": 0, "applied": apply, "actions": [{"path": p, "action": a} for p, a, _ in actions], "notes": notes,
            "kept": ["docs/", "memory/ records, receipts and events", "human-materials/"]}

