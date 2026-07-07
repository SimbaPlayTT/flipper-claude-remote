#!/usr/bin/env python3
"""PreToolUse hook (matcher: AskUserQuestion): mirror the question's options
onto the Flipper as a picker. Selecting one sends Down x idx + Enter to the
CLI's question UI; the hook itself never blocks or answers the tool."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") != "AskUserQuestion":
        return 0

    questions = (payload.get("tool_input") or {}).get("questions") or []
    if not questions:
        return 0
    # The CLI shows one question at a time; mirror the first one. The picker
    # drives the CLI's own selector, so multiSelect questions still work for
    # the first choice.
    q = questions[0]
    question = str(q.get("question", "") or "")
    options = [
        str(opt.get("label", "") or "")
        for opt in (q.get("options") or [])
        if isinstance(opt, dict)
    ]
    options = [o for o in options if o]
    if options:
        flipper_ipc.ask_options(question, options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
