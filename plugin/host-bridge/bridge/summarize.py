"""Summarize a turn's text with a small model before it goes to the Flipper.

Uses the Messages API with the user's own local Claude Code OAuth
credentials (same auth the CLI itself uses) and a Haiku-class model, so
summaries are quick and cheap. Synchronous — the daemon calls this in an
executor thread. Returns None on any failure; the caller falls back to
truncated raw text.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-haiku-4-5-20251001"
_MAX_INPUT_CHARS = 8000

_PROMPT = (
    "Summarize what the coding assistant did and said in this turn for a "
    "tiny 128x64 pixel device screen. At most 300 characters, plain ASCII, "
    "no markdown, no preamble - just the summary."
)


def _token() -> str | None:
    cred = Path.home() / ".claude" / ".credentials.json"
    try:
        return json.loads(cred.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
    except Exception:
        return None


def summarize(text: str) -> str | None:
    token = _token()
    if not token or not text.strip():
        return None
    body = json.dumps(
        {
            "model": _MODEL,
            "max_tokens": 200,
            "system": [
                {
                    "type": "text",
                    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                }
            ],
            "messages": [
                {"role": "user", "content": _PROMPT + "\n\n---\n" + text[-_MAX_INPUT_CHARS:]}
            ],
        }
    ).encode()
    req = urllib.request.Request(
        _ENDPOINT,
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        parts = [
            blk.get("text", "")
            for blk in data.get("content") or []
            if isinstance(blk, dict) and blk.get("type") == "text"
        ]
        summary = "\n".join(p for p in parts if p).strip()
        return summary or None
    except Exception as e:
        log.warning("Summarize failed: %s", e)
        return None
