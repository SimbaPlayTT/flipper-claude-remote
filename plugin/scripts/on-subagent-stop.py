#!/usr/bin/env python3
"""SubagentStop hook: play distinct tone and show agent result snippet on Flipper."""

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
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0

    agent_type = hook_input.get("agent_type", "Agent")
    last_msg = hook_input.get("last_assistant_message", "").strip()
    subtext = last_msg[:21] if last_msg else "stopped"

    # alert: single E5 blip + cyan flash, does NOT clear the working indicator
    flipper_ipc.notify("alert", False, f"{agent_type} agent", subtext)
    return 0


if __name__ == "__main__":
    sys.exit(main())
