#!/usr/bin/env python3
"""Stop hook: notify Flipper when Claude finishes a turn, with tool usage summary."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        flipper_ipc.remove_quiet(flipper_ipc.STATS_FILE)
        return 0

    # Skip "Turn complete" if a direct Flipper notify was sent this turn
    if os.path.isfile(flipper_ipc.SKIP_STOP_FLAG):
        flipper_ipc.remove_quiet(flipper_ipc.SKIP_STOP_FLAG, flipper_ipc.STATS_FILE)
        return 0

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}
    interrupted = bool(payload.get("interrupted", False))

    # Build compact summary from tool stats: "3 Edit 2 Bash"
    subtext = ""
    if os.path.isfile(flipper_ipc.STATS_FILE):
        try:
            with open(flipper_ipc.STATS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
            parts = sorted(stats.items(), key=lambda x: -x[1])
            summary = " ".join(f"{v} {k}" for k, v in parts)
            subtext = summary[:21] if summary else ""
        except Exception:
            subtext = ""
        flipper_ipc.remove_quiet(flipper_ipc.STATS_FILE)

    if interrupted:
        flipper_ipc.notify("interrupt", True, "Interrupted", subtext)
    else:
        flipper_ipc.notify("success", True, "Turn complete", subtext)

    return 0


if __name__ == "__main__":
    sys.exit(main())
