#!/usr/bin/env python3
"""Claude Code lifecycle hook for Dreamdocs project memory (issue #19); logic in scripts/lifecycle.py.

Built from documented Claude Code 2.1.273 payloads; not yet observed in an authenticated session.
"""
import hashlib
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import lifecycle


def turn(payload):
    """Claude's Stop has no turn_id: use prompt_id when present, else a hash of the final message."""
    if payload.get("prompt_id"):
        return str(payload["prompt_id"])
    message = payload.get("last_assistant_message") if isinstance(payload.get("last_assistant_message"), str) else ""
    return "msg-" + hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    raise SystemExit(lifecycle.main(ROOT, "claude-code", turn))
