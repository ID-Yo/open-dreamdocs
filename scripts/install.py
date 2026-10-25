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
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automation_contract as ac
import memory_capture as mc
import project_memory as pm

PACKAGE_VERSION = "1.5.0-rc.3"
BINDING, MANIFEST, HOOKS, AGENTS = "memory/automation.json", "memory/automation/install.json", ".codex/hooks.json", "AGENTS.md"
HOOKS_IGNORE = ".codex/.gitignore"
HOOK_SCRIPT, BLOCK_FILE = "adapters/codex/hook.py", "adapters/outcome-block.md"
LOCAL, BACKUP = ".dreamdocs", ".dreamdocs/backup"  # machine-local state; .dreamdocs/.gitignore ignores the folder
EVENTS = ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd")
TIMEOUTS = {"SessionStart": 15, "UserPromptSubmit": 10, "Stop": 30, "SessionEnd": 3}
BLOCK_START, BLOCK_END = "<!-- dreamdocs:automation:start -->", "<!-- dreamdocs:automation:end -->"
MEMORY_POLICY = ("Memory stays in this project folder: episodes and receipts are ordinary files you may commit; "
                 "memory/automation/events and pending are local and Git-ignored. Nothing is sent to a cloud service "
                 "and no model is called by the hooks.")
CLAUDE_EVENTS = ("SessionStart", "UserPromptSubmit", "Stop", "StopFailure", "SessionEnd")
CLAUDE_TIMEOUTS = {"SessionStart": 15, "UserPromptSubmit": 10, "Stop": 30, "StopFailure": 5, "SessionEnd": 3}
CLAUDE_TRUST = ("Open Claude Code in this project and review the Dreamdocs hooks if it asks; run /hooks to see them. "
                "The Claude Code adapter is unverified until an authenticated session has saved and recalled memory.")
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


def claude_version():
    """Installed Claude Code version from its npm package, without running the client; None when not found."""
    found = shutil.which("claude")
    if not found:
        return None
    package = Path(found).resolve().parent / "node_modules" / "@anthropic-ai" / "claude-code" / "package.json"
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


def tracked(root, relative):
    """True when Git tracks the file; False when it does not or Git is unavailable."""
    try:
        return subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", relative],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def hook_command(python, script):
    """A hook command for the shell Codex uses. Quoted arguments work in cmd and PowerShell; a quoted
    program does not, so the interpreter stays unquoted (or its 8.3 name is used) where possible."""
    script = f'"{script}"' if " " in str(script) else str(script)
    python = str(python)
    if " " in python:
        short = short_path(python)
        if short and " " not in short:
            python = short
    if " " not in python:
        return f"{python} -B {script}", None
    return (f'& "{python}" -B {script}',
            "the Python path has spaces and no short name; the hook uses the PowerShell call form, which Codex "
            "on Windows uses (verified with 0.147.0), so it will not run from cmd")


def newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def block_span(text):
    """Span of the first complete block whose markers are whole lines; marker text inside prose never counts."""
    position, start = 0, None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if bare == BLOCK_START and start is None:
            start = position
        elif bare == BLOCK_END and start is not None:
            return start, position + len(line)
        position += len(line)
    return None


def dangling_marker(text):
    return block_span(text) is None and any(line.rstrip("\r\n") == BLOCK_START for line in text.splitlines())


def block_digest(text):
    span = block_span(text)
    return pm.digest(text[span[0]:span[1]].replace("\r\n", "\n").encode()) if span else None


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


CLIENTS = {
    "codex": {"name": "Codex", "hook_file": HOOKS, "ignore": HOOKS_IGNORE, "folder": ".codex", "instructions": AGENTS,
              "script": HOOK_SCRIPT, "events": EVENTS, "timeouts": TIMEOUTS, "version": "codex_version",
              "missing": "Install Codex CLI (npm install -g @openai/codex), then run setup again.", "trust": TRUST_STEP},
    "claude-code": {"name": "Claude Code", "hook_file": ".claude/settings.local.json", "ignore": ".claude/.gitignore",
                    "folder": ".claude", "instructions": "CLAUDE.md", "script": "adapters/claude-code/hook.py",
                    "events": CLAUDE_EVENTS, "timeouts": CLAUDE_TIMEOUTS, "version": "claude_version",
                    "missing": "Install Claude Code (npm install -g @anthropic-ai/claude-code), then run setup again.",
                    "trust": CLAUDE_TRUST},
}


def is_ours(handler, script):
    if not isinstance(handler, dict):
        return False
    parts = [str(handler.get("command", ""))] + [str(a) for a in handler.get("args", []) if isinstance(handler.get("args"), list)]
    return any(p.replace("\\", "/").rstrip('"').endswith("/" + script) for p in parts)


def without_ours(data, script=HOOK_SCRIPT):
    """Remove Dreamdocs handlers; keep every other key, group and handler exactly."""
    hooks = data.get("hooks", {})
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        groups = []
        for group in hooks[event]:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list) and any(is_ours(h, script) for h in group["hooks"]):
                group = {**group, "hooks": [h for h in group["hooks"] if not is_ours(h, script)]}
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


def handler(client, root, event):
    spec = CLIENTS[client]
    if client == "codex":
        command, _ = hook_command(Path(sys.executable).absolute(), root / spec["script"])
        return {"type": "command", "command": command, "timeout": spec["timeouts"][event], "statusMessage": "Dreamdocs memory"}
    # exec form: no shell, so spaces in either path need no quoting; the project path stays a placeholder
    return {"type": "command", "command": str(Path(sys.executable).absolute()),
            "args": ["-B", "${CLAUDE_PROJECT_DIR}/" + spec["script"]], "timeout": spec["timeouts"][event]}


def merged_hooks(existing, client, root):
    spec = CLIENTS[client]
    data = without_ours(json.loads(json.dumps(existing)), spec["script"]) if existing is not None else {}
    hooks = data.setdefault("hooks", {})
    for event in spec["events"]:
        hooks.setdefault(event, []).append({"hooks": [handler(client, root, event)]})
    return data


def command_digest(record):
    """Hash of the generated Stop handler definition; manifests before the rename used hook_sha256."""
    return record.get("command_sha256") or record.get("hook_sha256")


def validate_manifest(value):
    """Validate the bundled install schema's shape without a runtime dependency."""
    schema = pm.read_json(Path(__file__).resolve().parents[1] / "templates/install-manifest.schema.json")
    types = {"object": dict, "array": list, "string": str, "integer": int, "null": type(None), "boolean": bool}

    def check(item, rule):
        if "anyOf" in rule:
            valid = False
            for option in rule["anyOf"]:
                try:
                    check(item, option)
                    valid = True
                except ValueError:
                    pass
            pm.require(valid, "manifest requires a current or legacy command hash")
        if "type" in rule:
            names = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
            pm.require(type(item) in tuple(types[n] for n in names), "invalid manifest field type")
        if "const" in rule:
            pm.require(item == rule["const"], "invalid manifest constant")
        if "enum" in rule:
            pm.require(item in rule["enum"], "invalid manifest value")
        if isinstance(item, dict):
            pm.require(set(rule.get("required", [])) <= item.keys(), "missing required manifest field")
            for key, child in item.items():
                selected = rule.get("properties", {}).get(key, rule.get("additionalProperties", {}))
                pm.require(selected is not False, "unknown manifest field: " + key)
                if isinstance(selected, dict):
                    check(child, selected)
        elif isinstance(item, list):
            for child in item:
                check(child, rule.get("items", {}))
        elif isinstance(item, str) and "pattern" in rule:
            pm.require(re.fullmatch(rule["pattern"], item), "invalid manifest hash")
    check(value, schema)
    return value


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


def plan(root, project_id=None, clients=("codex",), *, block_text=None, package_files=None):
    """Compute every write without performing it. Returns (report, writes, conflicts)."""
    root = Path(root).resolve()
    conflicts, warnings, writes, actions, order = [], [], {}, [], [BINDING]
    old = read(root, MANIFEST)
    previous = json.loads(old) if old else {}
    binding, text = None, read(root, BINDING)
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
    adapters = sorted(set(binding["adapters"] if binding else []) | set(clients))
    writes[BINDING] = json.dumps({"version": 1, "project_id": identity, "adapters": adapters}, indent=2) + "\n"
    package_root = Path(__file__).resolve().parents[1]
    block = block_text if block_text is not None else read(root, BLOCK_FILE)
    if block is None:
        block = read(package_root, BLOCK_FILE)
    if block is None or block_span(block) is None:
        conflicts.append((BLOCK_FILE, f"{BLOCK_FILE} must contain a complete Dreamdocs automation block; preserve and review the existing file before retrying."))
        block = "" if block is None else block
    clients_record, merged, report_clients, steps = dict(previous.get("clients", {})), dict(previous.get("merged", {})), {}, []
    created = set(previous.get("created", []))
    for client in clients:
        spec = CLIENTS[client]
        version = globals()[spec["version"]]()
        if version is None:
            conflicts.append(("client", spec["missing"]))
        hook_file, ignore = spec["hook_file"], spec["ignore"]
        existing = read(root, hook_file)
        if client == "codex" and not any((folder / ".git").exists() for folder in (root, *root.parents)):
            warnings.append("This folder is not inside a Git repository. Codex treats it as untrusted, and codex exec refuses to run "
                            "there (\"Not inside a trusted directory\") even after hooks are trusted. Run git init, or trust this "
                            "directory in Codex, before using it.")
        if client == "codex":
            _, warning = hook_command(Path(sys.executable).absolute(), root / spec["script"])
            warnings += [warning] if warning else []
        if existing is None and read(root, ignore) is None:
            writes[ignore] = Path(hook_file).name + "\n"  # the hook entries hold machine-local paths
        elif existing is not None and tracked(root, hook_file):
            warnings.append(f"{hook_file} is tracked by Git; after setup it holds machine-local paths for this computer, so do not commit it.")
        try:
            current = json.loads(existing) if existing is not None else None
            pm.require(current is None or isinstance(current, dict) and isinstance(current.get("hooks", {}), dict), "not a hooks object")
            writes[hook_file] = json.dumps(merged_hooks(current, client, root), indent=2, ensure_ascii=False) + "\n"
        except ValueError:
            conflicts.append((hook_file, f"Fix {hook_file}: it is not a valid JSON settings object. Setup never overwrites it."))
        if existing is not None and hook_file in writes and hook_file not in created and read(root, f"{BACKUP}/{hook_file}") is None:
            writes[f"{BACKUP}/{hook_file}"], writes[f"{LOCAL}/.gitignore"] = existing, "*\n"  # original bytes for uninstall
        if client == "codex":
            toml = read(root, ".codex/config.toml")
            if toml is not None and re.search(r"^\s*\[\[?hooks", toml, re.M):
                warnings.append(".codex/config.toml also defines hooks; Codex loads both and warns at startup.")
        doc = spec["instructions"]
        if doc not in writes:
            if dangling_marker(read(root, doc) or ""):
                conflicts.append((doc, f"{doc} has a {BLOCK_START} line without a matching end line; complete or remove it, then run setup again."))
            writes[doc], prefix = with_block(read(root, doc), block, merged.get(doc, {}).get("prefix"))
            merged[doc] = {"block": "dreamdocs:automation", "sha256": pm.digest(block.replace("\r\n", "\n").encode()), "prefix": prefix}
        created |= {p for p in (hook_file, ignore, doc) if read(root, p) is None and p in writes}
        clients_record[client] = {"version": version, "hook_file": hook_file, "events": list(spec["events"]),
                                  "command_sha256": pm.digest(json.dumps(handler(client, root, "Stop"), sort_keys=True).encode()),
                                  "trust": "pending", "probe": "pending",
                                  "written_sha256": pm.digest(writes[hook_file].encode()) if hook_file in writes else None}
        report_clients[client] = {"version": version, "support": ac.SUPPORT[client]["state"]}
        steps.append(spec["trust"])
        order += [hook_file, ignore, doc, f"{BACKUP}/{hook_file}"]
    package = sorted(path.relative_to(root).as_posix() for path in pm.managed_files(root)
                     if path.relative_to(root).parts[0] in {"scripts", "adapters"} or path.name.endswith(".schema.json"))
    known = previous.get("binding", {})
    added = set(known.get("added_adapters", [])) | (set(clients) - set(binding["adapters"] if binding else []))
    binding_record = {"created": known.get("created", binding is None and text is None), "added_adapters": sorted(added)}
    manifest = {"version": 1, "package": {"version": PACKAGE_VERSION}, "project_id": identity,
                "installed_at": previous.get("installed_at") or pm.now(), "python": platform.python_version(),
                "clients": dict(sorted(clients_record.items())),
                "package_files": package_files if package_files is not None else {p: pm.digest((root / p).read_bytes()) for p in package},
                "merged": dict(sorted(merged.items())), "created": sorted(created), "binding": binding_record,
                "user_owned": ["docs/", "memory/ records and receipts", "human-materials/", "PROJECT.md"],
                "local_only": ["memory/automation/events/", "memory/automation/pending/"] +
                              [f"absolute paths in {CLIENTS[c]['hook_file']}" for c in sorted(clients_record)]}
    if previous and {k: v for k, v in previous.items() if k != "installed_at"} == {k: v for k, v in manifest.items() if k != "installed_at"}:
        manifest = previous
    writes[MANIFEST] = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    for path in dict.fromkeys(order + [MANIFEST, f"{LOCAL}/.gitignore"]):
        if path in writes:
            before = read(root, path)
            actions.append({"path": path, "action": "create" if before is None else "unchanged" if before == writes[path] else "update"})
    hook = handler(clients[0], root, "Stop")
    report = {"root": str(root), "python": sys.executable, "project_id": identity, "clients": report_clients,
              "hook_command": " ".join([hook["command"], *hook.get("args", [])]),
              "actions": actions, "warnings": warnings, "memory_policy": MEMORY_POLICY, "removal": REMOVAL,
              "conflicts": [c for _, c in conflicts], "next_steps": [c for _, c in conflicts] or steps}
    return report, writes, conflicts


def setup(root, apply=False, project_id=None, clients=("codex",)):
    root = Path(root).resolve()
    report, writes, conflicts = plan(root, project_id, tuple(clients))
    package_root = Path(__file__).resolve().parents[1]
    required = {"scripts/" + p.name for p in (package_root / "scripts").glob("*.py")}
    required |= {BLOCK_FILE, "memory/config.json", "templates/outcome-event.schema.json", "templates/install-manifest.schema.json"}
    required |= {CLIENTS[c]["script"] for c in clients}
    missing = sorted(p for p in required if not pm.confined(root, p).is_file())
    if missing:
        message = ("Missing Dreamdocs package assets in target: " + ", ".join(missing) +
                   ". Setup configures existing package files; it does not copy them. "
                   "Selectively adopt the reviewed package under docs/operations/adopting-dreamdocs.md, preserving owner files, then retry.")
        conflicts.append(("package", message))
        report["conflicts"].append(message)
        report["next_steps"] = [c for _, c in conflicts]
    exit_code = 5 if any(kind != "client" for kind, _ in conflicts) else 4 if conflicts else 0
    report.update(exit=exit_code, applied=False, state="needs action" if conflicts else "planned; nothing written (use --apply)")
    if not apply or conflicts:
        return report
    for action in report["actions"]:
        if action["action"] != "unchanged":
            mc.atomic_text(pm.confined(root, action["path"]), writes[action["path"]])
    names = " and ".join(CLIENTS[c]["name"] for c in clients)
    report.update(applied=True, state=f"installed; {names} hook trust pending; probe pending")
    return report


def uninstall(root, apply=False):
    root = Path(root).resolve()
    manifest = json.loads(read(root, MANIFEST) or "{}")
    created, actions, notes = set(manifest.get("created", [])), [], []
    clients = [c for c in CLIENTS if c in manifest.get("clients", {})] or list(CLIENTS)
    docs = []
    for client in clients:
        spec = CLIENTS[client]
        hook_file = spec["hook_file"]
        hooks, backup = read(root, hook_file), read(root, f"{BACKUP}/{hook_file}")
        if hooks is not None:
            unchanged = pm.digest(hooks.encode()) == manifest.get("clients", {}).get(client, {}).get("written_sha256")
            data = without_ours(json.loads(hooks), spec["script"])
            if not data and hook_file in created:
                actions.append((hook_file, "delete", None))
            elif unchanged and backup is not None:
                actions.append((hook_file, "restore", backup))
            elif unchanged and hook_file not in created and backup is None:
                actions.append((hook_file, "update", json.dumps(data, indent=2, ensure_ascii=False) + "\n"))
            else:
                actions.append((hook_file, "update", json.dumps(data, indent=2, ensure_ascii=False) + "\n"))
                notes.append(f"{hook_file} changed after setup: Dreamdocs entries removed, other content kept, formatting not preserved")
        if backup is not None:
            actions.append((f"{BACKUP}/{hook_file}", "delete", None))
        if spec["ignore"] in created and read(root, spec["ignore"]) == Path(hook_file).name + "\n":
            actions.append((spec["ignore"], "delete", None))
        if spec["instructions"] not in docs:
            docs.append(spec["instructions"])
    for doc in docs:
        text = read(root, doc)
        merged = manifest.get("merged", {}).get(doc, {})
        if text is not None and block_span(text):
            if block_digest(text) != merged.get("sha256"):
                step = f"The Dreamdocs block in {doc} was edited after setup; remove it by hand (the lines from {BLOCK_START} to {BLOCK_END}), then run uninstall again."
                return {"exit": 5, "applied": False, "actions": [], "notes": notes, "next_steps": [step]}
            remaining = without_block(text, merged.get("prefix", ""))
            gone = not remaining.strip() and doc in created
            actions.append((doc, "delete" if gone else "update", None if gone else remaining))
    if read(root, f"{LOCAL}/.gitignore") is not None and any(a[0].startswith(BACKUP) for a in actions):
        actions.append((f"{LOCAL}/.gitignore", "delete", None))
    bound, record = read(root, BINDING), manifest.get("binding", {})
    if bound is not None and record.get("created"):
        actions.append((BINDING, "delete", None))
    elif bound is not None:  # the user's binding: take back only the adapters setup added
        data = json.loads(bound)
        data["adapters"] = [a for a in data.get("adapters", []) if a not in set(record.get("added_adapters", ["codex"]))]
        actions.append((BINDING, "update", json.dumps(data, indent=2) + "\n"))
    if read(root, MANIFEST) is not None:
        actions.append((MANIFEST, "delete", None))
    if apply:
        for path, action, text in actions:
            target = pm.confined(root, path)
            if action == "delete":
                target.unlink(missing_ok=True)
            elif text != read(root, path):
                mc.atomic_text(target, text)
        folders = [f"{BACKUP}/{CLIENTS[c]['folder']}" for c in clients] + [BACKUP, LOCAL]
        folders += [CLIENTS[c]["folder"] for c in clients if CLIENTS[c]["hook_file"] in created]
        for folder in folders:
            path = pm.confined(root, folder)
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    return {"exit": 0, "applied": apply, "actions": [{"path": p, "action": a} for p, a, _ in actions], "notes": notes, "next_steps": [],
            "kept": ["docs/", "memory/ records, receipts and events", "human-materials/"]}
