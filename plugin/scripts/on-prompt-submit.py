#!/usr/bin/env python3
"""UserPromptSubmit hook: show "Thinking..." on Flipper when the user sends a prompt."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402
import session_target  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}

    # Refresh the active input target from the session that just submitted a
    # prompt (on Windows this re-captures the terminal's foreground HWND).
    try:
        session_target.register_current_session("register_target")
    except Exception:
        pass

    # Echo the prompt into the Flipper's Terminal view and let the bridge
    # know which transcript this session writes (used by /usage, /context).
    prompt = str(payload.get("prompt", "") or "").strip()
    transcript_path = str(payload.get("transcript_path", "") or "")
    if prompt or transcript_path:
        text = ("> " + prompt[:400]) if prompt else ""
        flipper_ipc.term(text, transcript_path=transcript_path)

    flipper_ipc.display("Thinking...", "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
