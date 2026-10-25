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
import dreamer_executor as de
import materials_index as mi


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    groups = parser.add_subparsers(dest="group", required=True)
    dreamer = groups.add_parser("dreamer", help="Explicit executor workflow; no schedule is enabled by default.").add_subparsers(dest="command", required=True)
    for name in ("begin", "start", "finish", "run", "status"):
        command = dreamer.add_parser(name)
        if name != "status":
            command.add_argument("--executor", required=True)
        if name in {"start", "finish"}:
            command.add_argument("--run-id", required=True)
        if name == "run":
            command.add_argument("--trigger", choices=["manual", "scheduled"], default="manual")
            command.add_argument("--schedule-id")
    schedule = dreamer.add_parser("schedule", help="Separately opt-in Windows scheduler; mutations require --apply.")
    schedule.add_argument("action", choices=["install", "status", "disable", "remove"])
    schedule.add_argument("--apply", action="store_true")
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
    rollback = groups.add_parser("rollback", help="Plan or restore one private upgrade transaction while preserving later memory.")
    rollback.add_argument("--backup", required=True, help="Exact project-relative .dreamdocs/backups/<transaction> directory.")
    rollback.add_argument("--apply", action="store_true")
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
    materials = groups.add_parser("materials", help="Human Materials indexing: mode (owner consent), scan, index, status.").add_subparsers(dest="command", required=True)
    mode = materials.add_parser("mode", help="Record the owner's choice: off, inventory or summarize.")
    mode.add_argument("value", choices=list(mi.MODES))
    for name in ("scan", "index"):
        command = materials.add_parser(name)
        command.add_argument("--apply", action="store_true", help="Write index rows and state (default is a read-only plan).")
        if name == "index":
            command.add_argument("--trigger", choices=["manual", "session", "dreamer"], default="manual")
    materials.add_parser("status")
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
        if args.group == "materials":
            if args.command == "mode":
                result = mi.set_mode(root, args.value)
            elif args.command == "scan":
                result = mi.scan_locked(root, args.apply)
            elif args.command == "index":
                result = mi.index(root, args.apply, args.trigger)
            else:
                result = mi.status(root)
        elif args.group == "dreamer":
            if args.command == "schedule":
                import dreamer_schedule
                result = dreamer_schedule.manage(root, args.action, args.apply)
            elif args.command == "status":
                result = de.status(root)
            elif args.command == "begin":
                result = de.begin(root, args.executor)
            elif args.command == "start":
                result = de.start(root, args.run_id, args.executor)
            elif args.command == "finish":
                result = de.finish(root, args.run_id, args.executor)
            else:
                result = de.run(root, args.executor, args.trigger, args.schedule_id)
        elif args.group in {"upgrade", "update"}:
            if args.apply and args.dry_run:
                raise ValueError("choose --apply or --dry-run")
            result = upgrade.update(root, args.source, args.manifest_sha256, args.revision, args.apply, args.from_version, args.client)
        elif args.group == "rollback":
            result = upgrade.rollback(root, args.backup, args.apply)
        elif args.group == "bundle-manifest":
            print(json.dumps(upgrade.bundle_manifest(root, args.revision), sort_keys=True, indent=2))
            return 0
        elif args.group in {"doctor", "status"}:
            evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8")) if args.evidence is not None else mh.UNSET
            checkpoints = json.loads(Path(args.checkpoints).read_text(encoding="utf-8")) if args.checkpoints else None
            result = mh.doctor(root, args.fix, args.smoke, evidence=evidence, checkpoints=checkpoints)
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

