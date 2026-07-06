#!/usr/bin/env python3
"""PostToolUse hook: plays a per-tool sound on the Flipper after each tool call."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402

# Map tool names (or prefixes) to sound names.
# Evaluated in order — first match wins.
TOOL_SOUNDS = [
    ({"Edit", "Write", "NotebookEdit"},         "enter"),   # file write: soft blip
    ({"Bash"},                                   "cmd"),     # shell command: confirm tone
    ({"WebFetch", "WebSearch"},                  "alert"),   # network: attention tone
    ({"Read"},                                   "enter"),   # read-only: soft blip
    ({"Glob", "Grep"},                           None),      # read-only: silent
]

# Bash commands that talk to the bridge directly (e.g. the flipper-notify
# skill) already set their own display — recognisable by these markers.
DIRECT_NOTIFY_MARKERS = ("claude-flipper-bridge", "flipper-notify")


def sound_for_tool(tool_name: str) -> str | None:
    for tools, sound in TOOL_SOUNDS:
        if tool_name in tools:
            return sound
    return None  # unknown tools: silent


def tool_detail(tool_name: str, hook_input: dict) -> str:
    """Extract a short detail string from the tool input."""
    tool_input = hook_input.get("tool_input", {})
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:21] if cmd else ""
    if tool_name in ("Edit", "Write", "Read"):
        path = tool_input.get("file_path", "")
        return os.path.basename(path)[:21] if path else ""
    if tool_name in ("WebFetch", "WebSearch"):
        val = tool_input.get("url") or tool_input.get("query", "")
        for prefix in ("https://", "http://"):
            if val.startswith(prefix):
                val = val[len(prefix):]
                break
        return val[:21]
    return ""


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 0

    tool_name = hook_input.get("tool_name", "")

    # Skip notification for Bash commands that write to the bridge directly —
    # they already set their own display. Also flag the stop hook to skip
    # "Turn complete" for this turn.
    if tool_name == "Bash":
        cmd = hook_input.get("tool_input", {}).get("command", "")
        if any(marker in cmd for marker in DIRECT_NOTIFY_MARKERS):
            try:
                open(flipper_ipc.SKIP_STOP_FLAG, "w").close()
            except Exception:
                pass
            return 0

    # Track tool usage stats for the Stop hook summary
    try:
        stats = (
            json.loads(open(flipper_ipc.STATS_FILE).read())
            if os.path.exists(flipper_ipc.STATS_FILE)
            else {}
        )
    except Exception:
        stats = {}
    stats[tool_name] = stats.get(tool_name, 0) + 1
    try:
        open(flipper_ipc.STATS_FILE, "w").write(json.dumps(stats))
    except Exception:
        pass

    sound = sound_for_tool(tool_name)
    if not sound:
        return 0

    detail = tool_detail(tool_name, hook_input)
    flipper_ipc.send_request(
        {"action": "notify", "sound": sound, "vibro": False, "text": tool_name, "subtext": detail}
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
