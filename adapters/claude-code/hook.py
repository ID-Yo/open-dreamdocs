#!/usr/bin/env python3
"""Claude Code lifecycle hook for Dreamdocs project memory (issue #19); logic in scripts/lifecycle.py.

Built from documented Claude Code 2.1.273 payloads; not yet observed in an authenticated session.
"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import lifecycle


def turn(payload):
    """Only a client prompt identity can distinguish identical replies in different turns."""
    if payload.get("prompt_id"):
        return str(payload["prompt_id"])
    return None


if __name__ == "__main__":
    raise SystemExit(lifecycle.main(ROOT, "claude-code", turn))
