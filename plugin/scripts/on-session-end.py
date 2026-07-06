#!/usr/bin/env python3
"""SessionEnd hook: notify Flipper of disconnect, then stop the bridge
when the last session ends (reference-counted).

Cross-platform port of the upstream shell hook. The daemon is stopped via
the 'shutdown' IPC action so it can disconnect BLE cleanly; process kill is
only a fallback.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402
import session_target  # noqa: E402

REASONS = {
    "clear": "Cleared",
    "resume": "Switched session",
    "logout": "Logged out",
    "prompt_input_exit": "User exited",
    "bypass_permissions_disabled": "Bypass perms off",
    "other": "Disconnected",
}


def read_reason_from_payload() -> str:
    try:
        data = json.loads(sys.stdin.read())
        raw = data.get("reason") or ""
        return REASONS.get(raw, raw or "Disconnected")[:21]
    except Exception:
        return "Disconnected"


def main() -> int:
    reason = read_reason_from_payload()

    # Decrement session reference counter
    try:
        count = int(Path(flipper_ipc.REFCOUNT_FILE).read_text().strip())
    except Exception:
        count = 1
    count = max(count - 1, 0)
    try:
        Path(flipper_ipc.REFCOUNT_FILE).write_text(str(count))
    except OSError:
        pass

    if flipper_ipc.bridge_available():
        try:
            session_target.register_current_session("release_target")
        except Exception:
            pass
        flipper_ipc.send_request({"action": "claude_disconnect"})

    # Only stop bridge when the last session ends
    if count <= 0:
        if flipper_ipc.bridge_available():
            flipper_ipc.notify("session_end", True, "Session End", reason)
            # Give the bridge time to deliver the message to the Flipper
            time.sleep(0.5)

        pid = flipper_ipc.read_pid()
        if flipper_ipc.bridge_available():
            flipper_ipc.send_request({"action": "shutdown"}, timeout=3.0)
            for _ in range(30):
                if pid is not None and not flipper_ipc.pid_alive(pid):
                    break
                time.sleep(0.1)
        if pid is not None and flipper_ipc.pid_alive(pid):
            flipper_ipc.kill_pid(pid)

        flipper_ipc.remove_quiet(
            flipper_ipc.PID_FILE,
            flipper_ipc.REFCOUNT_FILE,
            flipper_ipc.SOCKET_PATH,
            flipper_ipc.PORT_FILE,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
