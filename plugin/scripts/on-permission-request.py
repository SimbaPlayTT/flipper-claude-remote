#!/usr/bin/env python3
"""PermissionRequest hook: shows permission request on Flipper, waits for user decision."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402

TIMEOUT = 60  # seconds to wait for user decision on Flipper


def extract_detail(tool_name: str, tool_input: dict) -> str:
    """Extract a short detail string from the tool input."""
    # Special handling for mcp__atlassian__searchJiraIssuesUsingJql and similar
    if "__" in tool_name:
        parts = tool_name.split("__")
        if len(parts) >= 3:
            # e.g. mcp__atlassian__searchJiraIssuesUsingJql
            return parts[-1][:21]
    if tool_name == "Bash":
        desc = tool_input.get("description", "")
        if desc:
            return desc[:21]
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
    if tool_name == "Agent":
        return tool_input.get("description", "")[:21]
    return ""


def main() -> int:
    if not flipper_ipc.bridge_available():
        # Bridge not running — fall back to normal permission dialog
        return 1

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        return 1

    tool_name_raw = hook_input.get("tool_name", "Unknown")
    tool_input = hook_input.get("tool_input", {})

    # For tool_name like mcp__atlassian__searchJiraIssuesUsingJql, display as mcp_atlassian
    if "__" in tool_name_raw:
        parts = tool_name_raw.split("__")
        if len(parts) >= 2:
            tool_name = f"{parts[0]}_{parts[1]}"
        else:
            tool_name = tool_name_raw
    else:
        tool_name = tool_name_raw

    detail = extract_detail(tool_name_raw, tool_input)

    result = flipper_ipc.send_request(
        {"action": "permission_request", "tool": tool_name, "detail": detail},
        timeout=TIMEOUT,
    )
    if result is None:
        # Bridge error — fall back to normal permission dialog
        return 1

    status = result.get("status")

    # Dismissed on Flipper — defer to Claude's normal permission dialog
    if status == "ask":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "ask"},
            }
        }))
        return 0

    # Only act on explicit user decisions from Flipper
    if status != "ok":
        # no_flipper, timeout, busy, error — fall back to normal dialog
        return 1

    allowed = result.get("allowed", False)
    always = result.get("always", False)

    if allowed:
        decision = {"behavior": "allow"}
        if always:
            suggestions = hook_input.get("permission_suggestions", [])
            if suggestions:
                decision["updatedPermissions"] = suggestions
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": decision,
            }
        }
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": "Denied on Flipper"},
            }
        }

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
