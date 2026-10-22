#!/usr/bin/env python3
"""Dreamdocs command entry point: memory capture, reconcile and recall. Setup (#15) extends it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import memory_capture as mc
import memory_recall as mr


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    groups = parser.add_subparsers(dest="group", required=True)
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
        if args.command == "capture":
            event = json.loads(Path(args.event).read_text(encoding="utf-8"))
            result = mc.capture(root, event, max(args.budget_ms, 0) / 1000)
        elif args.command == "recall":
            result = mr.recall(root, args.project, args.query, args.max_chars, args.episodes)
        else:
            result = mc.reconcile(root)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())

