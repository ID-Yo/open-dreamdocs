#!/usr/bin/env python3
"""Dreamdocs command entry point: setup, uninstall and memory capture, reconcile and recall."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import install
import memory_capture as mc
import memory_recall as mr
import memory_health as mh
import upgrade


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    groups = parser.add_subparsers(dest="group", required=True)
    update = groups.add_parser("upgrade", aliases=["update"], help="Plan or apply an explicitly selected, independently pinned offline package.")
    update.add_argument("--source", required=True)
    update.add_argument("--revision", required=True, help="Independently reviewed upstream revision (40 hexadecimal characters).")
    update.add_argument("--manifest-sha256", required=True, help="Expected manifest pin obtained through trusted review, independently of bundle contents.")
    update.add_argument("--apply", action="store_true")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--from-version", choices=["v1.4.0"])
    update.add_argument("--client", action="append", choices=sorted(install.CLIENTS))
    bundle = groups.add_parser("bundle-manifest", help="Print a publisher-side package inventory; self-declared hashes are not source authentication.")
    bundle.add_argument("--revision", required=True)
    doctor = groups.add_parser("doctor", aliases=["status"], help="Report memory health; read-only unless --fix is explicit.")
    doctor.add_argument("--fix", action="store_true", help="Update install evidence metadata only; never remove locks or queued data.")
    doctor.add_argument("--smoke", action="store_true", help="Write/read/recall synthetic data in an isolated temporary project.")
    doctor.add_argument("--evidence", help="Explicit JSON file of source-backed real client observations.")
    doctor.add_argument("--checkpoints", help="Explicit JSON array joining task IDs and expected event receipts.")
    for name, text in (("setup", "Plan (default) or apply project-scoped Codex automation."), ("uninstall", "Plan (default) or remove what setup wrote.")):
        command = groups.add_parser(name, help=text)
        command.add_argument("--apply", action="store_true", help="Write the planned changes.")
        if name == "setup":
            command.add_argument("--project-id", help="Project identity for a new binding.")
            command.add_argument("--client", action="append", choices=sorted(install.CLIENTS),
                                 help="Client to set up (repeatable); default codex.")
    memory = groups.add_parser("memory").add_subparsers(dest="command", required=True)
    capture = memory.add_parser("capture", help="Persist one outcome event file (exact bytes written by the adapter).")
    capture.add_argument("--event", required=True)
    capture.add_argument("--budget-ms", type=int, default=1000, help="Wait at most this long for the writer lock, then queue.")
    memory.add_parser("reconcile", help="Publish queued captures once the writer lock is free.")
    recall = memory.add_parser("recall", help="Print relevant project memory as bounded, untrusted context.")
    recall.add_argument("--project", help="Project ID; defaults to memory/automation.json.")
    recall.add_argument("--query", default="", help="Session or prompt text used for deterministic matching.")
    recall.add_argument("--max-chars", type=positive, default=4000)
    recall.add_argument("--episodes", type=positive, default=5)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        if args.group in {"upgrade", "update"}:
            if args.apply and args.dry_run:
                raise ValueError("choose --apply or --dry-run")
            result = upgrade.update(root, args.source, args.manifest_sha256, args.revision, args.apply, args.from_version, args.client)
        elif args.group == "bundle-manifest":
            print(json.dumps(upgrade.bundle_manifest(root, args.revision), sort_keys=True, indent=2))
            return 0
        elif args.group in {"doctor", "status"}:
            evidence_supplied = args.evidence is not None
            evidence = (json.loads(Path(args.evidence).read_text(encoding="utf-8")), True) if evidence_supplied else None
            checkpoints = json.loads(Path(args.checkpoints).read_text(encoding="utf-8")) if args.checkpoints else None
            result = mh.doctor(root, args.fix, args.smoke, evidence, checkpoints)
        elif args.group == "setup":
            result = install.setup(root, args.apply, args.project_id, tuple(dict.fromkeys(args.client or ["codex"])))
        elif args.group == "uninstall":
            result = install.uninstall(root, args.apply)
        elif args.command == "capture":
            event = json.loads(Path(args.event).read_text(encoding="utf-8"))
            result = mc.capture(root, event, max(args.budget_ms, 0) / 1000)
        elif args.command == "recall":
            result = mr.recall(root, args.project, args.query, args.max_chars, args.episodes)
        else:
            result = mc.reconcile(root)
    except (OSError, ValueError) as exc:
        if args.group in {"doctor", "status"}:
            print(json.dumps({"exit": 2, "applied": False, "findings": [{"code": "unavailable_input", "component": "doctor",
                "scope": "explicit input", "next_action": "Inspect the explicitly selected local JSON inputs and retry.",
                "cause": type(exc).__name__}]}))
            return 2
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))  # ASCII-escaped: safe in any console code page
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())

