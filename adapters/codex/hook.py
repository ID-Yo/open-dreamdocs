#!/usr/bin/env python3
"""Codex lifecycle hook for Dreamdocs project memory (issue #18); logic in scripts/lifecycle.py."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import lifecycle


def turn(payload):
    return str(payload["turn_id"]) if payload.get("turn_id") else None


if __name__ == "__main__":
    raise SystemExit(lifecycle.main(ROOT, "codex", turn))
