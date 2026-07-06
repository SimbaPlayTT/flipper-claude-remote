#!/usr/bin/env python3
"""SubagentStart hook: show spawned agent type on Flipper."""

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
    flipper_ipc.display(f"{agent_type} agent", "started")
    return 0


if __name__ == "__main__":
    sys.exit(main())
