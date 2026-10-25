"""Audit an exact public Git snapshot/history and build a reproducible source ZIP; never publish."""
import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

import human_materials as hm
import project_memory as pm
import upgrade

ROOT_FILES = {"README.md", "AGENTS.md", "PROJECT.md", "CHANGELOG.md", "DESIGN_NOTES.md", "LICENSE", ".gitignore"}
PUBLIC_DIRS = {"docs", "scripts", "tests", "templates", "examples", "prompts", "adapters"}
SCAFFOLD = {"memory/config.json", "memory/README.md", "memory/SCHEMA.md", "memory/DREAMER_POLICY.md",
            "memory/archive/README.md", "memory/episodes/README.md", "memory/facts/README.md", "memory/procedural/README.md",
            "memory/contradictions/README.md", "memory/dreamer/README.md", "memory/dreamer/reports/README.md",
            "memory/dreamer/proposals/README.md", "memory/automation/README.md", "memory/automation/receipts/README.md",
            "human-materials/README.md", "human-materials/.gitignore"}
SECRET = re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{16,}|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----")
# Reviewed unsafe-input fixture contains only a synthetic header marker, explicitly no key material.
# Whole-blob SHA-256 exception, never a directory/pattern exception for test files.
SYNTHETIC_MARKER_BLOBS = {"43da2685a25718c3b2a6dd96cc276c265a62134d57c6826467bd6ec331718cb7"}


def allowed(path):
    parts = PurePosixPath(path).parts
    return (bool(parts) and ".." not in parts and "\\" not in path and ":" not in path
            and not any(p.casefold() in {"team", "raw", ".git", ".codex", ".claude", ".agents", ".bot-mode", ".dreamdocs", "node_modules", "__pycache__"}
                        or p.casefold().startswith(".env") for p in parts)
            and (path in ROOT_FILES or path in SCAFFOLD or parts[0] in PUBLIC_DIRS))


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def prepare(root, revision, output=None):
    root = Path(root).resolve()
    findings = []
    report = {"ok": False, "exit": 2, "findings": findings, "history_audited": False,
              "publication_authorized": False, "limits": "Inventory/secret-pattern checks are not runtime, semantic or publication acceptance. Review exact archive and release gates independently."}
    def git(*args, data=None):
        result = subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True, timeout=60)
        pm.require(result.returncode == 0, "Git snapshot/history inspection failed")
        return result.stdout
    def issue(scope, code, path=None):
        findings.append({"scope": scope, "code": code, **({"path": path} if path else {})})
    try:
        pm.require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision), "select the full exact reviewed commit SHA")
        pm.require(git("rev-parse", "--verify", revision + "^{commit}").decode().strip() == revision, "revision does not identify an exact commit")
        pm.require(git("rev-parse", "HEAD").decode().strip() == revision, "checkout must match the selected candidate")
        pm.require(not git("status", "--porcelain", "--untracked-files=no"), "tracked source edits are not a reviewed commit")
        records = git("ls-tree", "-rz", revision).split(b"\0")
        paths = {}
        for entry in records:
            if not entry:
                continue
            header, raw_name = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            name = raw_name.decode("utf-8")
            if mode not in {"100644", "100755"} or kind != "blob":
                issue("snapshot", "linked_or_nonfile_entry", name)
            if not allowed(name):
                issue("snapshot", "private_or_unapproved_path", name)
            paths[name] = oid
        objects = git("rev-list", "--objects", revision).splitlines()
        all_ids = []
        for item in objects:
            oid, _, name = item.partition(b" ")
            all_ids.append(oid)
            if name:
                decoded = name.decode("utf-8")
                if not allowed(decoded) and not any(p.startswith(decoded + "/") for p in SCAFFOLD):
                    issue("history", "private_or_unapproved_history_path", decoded)
        # Annotated tag messages are not reachable from a commit; include every local tag object.
        all_ids = list(dict.fromkeys(all_ids + git("for-each-ref", "--format=%(objectname)", "refs/tags").splitlines()))
        pm.require(len(all_ids) <= 20000, "history exceeds bounded audit; perform an independent offline audit")
        sizes = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", data=b"\n".join(all_ids) + b"\n").splitlines()
        content_ids = []
        for line in sizes:
            oid, kind, size = line.split()
            if kind in {b"blob", b"commit", b"tag"}:
                pm.require(int(size) <= 4194304, "history blob exceeds 4 MiB audit bound")
                content_ids.append(oid)
        pm.require(sum(int(line.split()[2]) for line in sizes) <= 100000000, "history exceeds 100 MB audit bound")
        packed = git("cat-file", "--batch", data=b"\n".join(content_ids) + b"\n")
        blobs, position, synthetic = {}, 0, 0
        for oid in content_ids:
            end = packed.index(b"\n", position)
            actual, kind, size = packed[position:end].split()
            pm.require(actual == oid and kind in {b"blob", b"commit", b"tag"}, "unexpected history object response")
            position = end + 1; body = packed[position:position + int(size)]; position += int(size) + 1
            if kind == b"blob":
                blobs[oid.decode()] = body
            if SECRET.search(body):
                if kind == b"blob" and pm.digest(body) in SYNTHETIC_MARKER_BLOBS:
                    synthetic += 1
                else:
                    issue("history", "credential_pattern" if kind == b"blob" else "credential_message", oid.decode())  # never echo a matched credential
        index_versions = set()
        for commit in git("log", "--full-history", "--format=%H", revision, "--", "human-materials/README.md").splitlines():
            for entry in git("ls-tree", commit.decode(), "--", "human-materials/README.md").splitlines():
                header, _ = entry.split(b"\t", 1)
                mode, kind, oid = header.split()
                pm.require(kind == b"blob" and mode in {b"100644", b"100755"}, "unsafe historical material index")
                index_versions.add(oid.decode())
        for oid in sorted(index_versions):
            old_index = blobs[oid].decode("utf-8-sig").replace("\r\n", "\n")
            if pm.digest(old_index.encode()) not in hm.KNOWN_EMPTY_INDEX_SHA256:
                issue("history", "nonempty_or_modified_material_index", oid)
        report["history_audited"] = True
        report["historical_material_index_versions"] = len(index_versions)
        report["synthetic_fixture_exceptions"] = synthetic
        files = {name: blobs[oid] for name, oid in paths.items()}
        required = {"README.md", "LICENSE", "scripts/install.py", "scripts/dreamdocs.py", "scripts/project_memory.py", "adapters/outcome-block.md", "human-materials/README.md"}
        pm.require(required <= files.keys(), "incomplete public package")
        index = files["human-materials/README.md"].decode("utf-8-sig").replace("\r\n", "\n")
        if pm.digest(index.encode()) != hm.EMPTY_INDEX_SHA256:
            issue("snapshot", "nonempty_or_modified_material_index", "human-materials/README.md")
        if "memory/config.json" in files:
            config = json.loads(files["memory/config.json"])
            if config != {"version": 1, "schedule": {"frequency": "daily", "timezone": None, "local_time": None, "owner": None}, "review": {"episode_days": None}}:
                issue("snapshot", "populated_runtime_configuration", "memory/config.json")
        tree = ast.parse(files["scripts/install.py"].decode())
        versions = [n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                    and any(isinstance(t, ast.Name) and t.id == "PACKAGE_VERSION" for t in n.targets)]
        pm.require(len(versions) == 1 and isinstance(versions[0], str), "missing package version stamp")
        if findings:
            return report
        hashes = {name: pm.digest(body) for name, body in sorted(files.items())}
        manifest = {"version": 1, "upstream": upgrade.UPSTREAM, "revision": revision, "package_version": versions[0], "memory_schema": 1,
                    "files": {name: sha for name, sha in hashes.items() if upgrade.package_asset(name)}}
        files["dreamdocs-release.json"] = json_bytes(manifest)
        hashes["dreamdocs-release.json"] = pm.digest(files["dreamdocs-release.json"])
        files["release-package.json"] = json_bytes({"version": 1, "revision": revision, "package_version": versions[0],
            "includes_git_history": False, "files": dict(sorted(hashes.items())), "publication_authorized": False})
        report.update(ok=True, exit=0, revision=revision, package_version=versions[0], files=len(files),
                      manifest_sha256=hashes["dreamdocs-release.json"], inventory_sha256=pm.digest(files["release-package.json"]))
        if output is not None:
            destination = Path(output).resolve()
            pm.require(not destination.is_relative_to(root), "write the release artifact outside the source checkout")
            pm.require(not destination.exists(), "refuse to overwrite an existing artifact")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                    for name, body in sorted(files.items()):
                        info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = 0o100644 << 16
                        archive.writestr(info, body)
            report.update(output=str(destination), archive_sha256=pm.digest(destination.read_bytes()))
        return report
    except (OSError, ValueError, TypeError, KeyError, SyntaxError, subprocess.SubprocessError) as error:
        report.update(ok=False, exit=2)
        issue("package", type(error).__name__)
        report["next_action"] = str(error)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", help="New ZIP outside the source tree; omit for audit only.")
    args = parser.parse_args()
    result = prepare(args.root, args.revision, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
