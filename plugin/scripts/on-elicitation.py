#!/usr/bin/env python3
"""Elicitation hook: notifies Flipper when Claude asks the user for input."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def extract_subtext(hook_input: dict) -> str:
    """Build a short subtext from the elicitation payload."""
    # Prefer MCP server name if present
    mcp = hook_input.get("mcp_server_name", "")
    if mcp:
        return mcp[:21]
    # Fall back to first line of message
    message = hook_input.get("message", "")
    first_line = message.split("\n", 1)[0].strip()
    return first_line[:21] if first_line else "Input needed"


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0

    flipper_ipc.notify("alert", True, "Elicitation", extract_subtext(hook_input))
    return 0


if __name__ == "__main__":
    sys.exit(main())
