#!/usr/bin/env python3
"""PostToolUseFailure hook: plays an error sound on the Flipper when a tool call fails."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def extract_subtext(hook_input: dict) -> str:
    """Extract a short, readable error summary for the Flipper display."""
    error = hook_input.get("error", "")
    tool_input = hook_input.get("tool_input", {})
    tool_name = hook_input.get("tool_name", "")

    # For Bash failures, show the first meaningful line of the error
    if tool_name == "Bash":
        for line in error.splitlines():
            line = line.strip()
            # Skip the generic "Exit code N" prefix
            if line.startswith("Exit code"):
                continue
            if line:
                return line[:21]

    # For file tools, show the basename
    if tool_name in ("Edit", "Write", "Read"):
        path = tool_input.get("file_path", "")
        if path:
            return os.path.basename(path)[:21]

    # Generic: first non-empty line of error
    for line in error.splitlines():
        line = line.strip()
        if line:
            return line[:21]

    return "Failed"


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0

    tool_name = hook_input.get("tool_name", "")
    flipper_ipc.notify("error", True, f"{tool_name} failed", extract_subtext(hook_input))
    return 0


if __name__ == "__main__":
    sys.exit(main())
