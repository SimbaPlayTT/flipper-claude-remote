#!/usr/bin/env python3
"""Notification hook: forwards relevant Claude Code notifications to Flipper."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402

NOTIFY_MAP = {
    "idle_prompt": ("alert", "Claude", "Waiting for input"),
}


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0

    notification_type = hook_input.get("notification_type", "")
    entry = NOTIFY_MAP.get(notification_type)
    if not entry:
        return 0

    sound, text, subtext = entry
    flipper_ipc.notify(sound, True, text, subtext)
    return 0


if __name__ == "__main__":
    sys.exit(main())
