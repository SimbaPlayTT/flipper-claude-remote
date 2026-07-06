#!/usr/bin/env python3
"""UserPromptSubmit hook: show "Thinking..." on Flipper when the user sends a prompt."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402
import session_target  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    # Refresh the active input target from the session that just submitted a
    # prompt (on Windows this re-captures the terminal's foreground HWND).
    try:
        session_target.register_current_session("register_target")
    except Exception:
        pass

    flipper_ipc.display("Thinking...", "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
