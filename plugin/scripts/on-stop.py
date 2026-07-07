#!/usr/bin/env python3
"""Stop hook: notify Flipper when Claude finishes a turn, with tool usage summary."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


MAX_REPLY_CHARS = 3000


def turn_text(transcript_path: str) -> str:
    """All assistant text of the just-finished turn: every text block after
    the most recent *real* user prompt (tool-result user entries don't end
    the walk). Mirrors what the CLI printed during the turn."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ""
    collected: list[str] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except Exception:
            continue
        etype = entry.get("type")
        msg = entry.get("message") or {}
        if etype == "assistant":
            parts = [
                blk.get("text", "")
                for blk in (msg.get("content") or [])
                if isinstance(blk, dict) and blk.get("type") == "text"
            ]
            text = "\n".join(p for p in parts if p).strip()
            if text:
                collected.append(text)
        elif etype == "user":
            content = msg.get("content")
            if isinstance(content, str):
                break  # real user prompt reached
            if isinstance(content, list) and any(
                isinstance(blk, dict) and blk.get("type") == "text" for blk in content
            ):
                break  # real user prompt reached (tool results keep walking)
    collected.reverse()
    text = "\n\n".join(collected)
    if len(text) > MAX_REPLY_CHARS:
        text = "[...] " + text[-MAX_REPLY_CHARS:].lstrip()
    return text


def main() -> int:
    if not flipper_ipc.bridge_available():
        flipper_ipc.remove_quiet(flipper_ipc.STATS_FILE)
        return 0

    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}
    interrupted = bool(payload.get("interrupted", False))

    # Stream a PC-side summary of the turn into the Flipper's Terminal view
    # (the bridge condenses the raw text with a small model, async).
    reply = turn_text(str(payload.get("transcript_path", "") or ""))
    if reply:
        flipper_ipc.term(
            reply,
            transcript_path=str(payload.get("transcript_path", "") or ""),
            summarize=True,
        )

    # Skip "Turn complete" if a direct Flipper notify was sent this turn
    if os.path.isfile(flipper_ipc.SKIP_STOP_FLAG):
        flipper_ipc.remove_quiet(flipper_ipc.SKIP_STOP_FLAG, flipper_ipc.STATS_FILE)
        return 0

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
