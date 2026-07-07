"""Render slash-command views for the Flipper terminal.

When the user picks one of VIEW_COMMANDS from the Flipper's command menu,
the bridge answers on the Flipper's Terminal view instead of typing the
command into the host terminal. All data comes from local Claude Code
transcripts (``~/.claude/projects/**/*.jsonl``) and bridge state — no
network calls. Numbers are therefore estimates of local activity, not the
account-level figures the real ``/usage`` screen shows.

Everything here is synchronous file I/O — the daemon calls render() in an
executor thread.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path

# The Flipper renders FontSecondary at ~5 px/char in a 123 px window.
WIDTH = 24

VIEW_COMMANDS = {"/usage", "/context", "/cost", "/status", "/stats"}

_RUNTIME_DIR = tempfile.gettempdir() if sys.platform == "win32" else "/tmp"
_STATS_FILE = os.path.join(_RUNTIME_DIR, "claude-flipper-turn-stats.json")

# Rough USD per 1M tokens (input, output) by model-name substring. Cache
# reads are billed at ~10% of input, cache writes at ~125%. Estimates only.
_PRICING = [
    ("haiku", (1.0, 5.0)),
    ("sonnet", (3.0, 15.0)),
    ("opus", (15.0, 75.0)),
    ("fable", (25.0, 125.0)),
    ("mythos", (25.0, 125.0)),
]
_DEFAULT_PRICE = (15.0, 75.0)


def sanitize(line: str) -> str:
    """Make a line safe for the Flipper's minimal JSON parser: ASCII only,
    no '|' (message delimiter), '"' or '\\' (would break the JSON string —
    the on-device parser does no unescaping), no control chars."""
    line = line.replace("|", "!").replace('"', "'").replace("\\", "/")
    line = "".join(c if 32 <= ord(c) < 127 else " " for c in line)
    return line


def wrap_text(text: str, width: int = WIDTH) -> list[str]:
    """Greedy word-wrap preserving explicit newlines; blank lines kept."""
    out: list[str] = []
    for para in text.splitlines() or [""]:
        para = sanitize(para.rstrip())
        if not para:
            out.append("")
            continue
        while len(para) > width:
            cut = para.rfind(" ", 1, width + 1)
            if cut <= 0:
                cut = width
            out.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        if para:
            out.append(para)
    return out


def header_line(title: str) -> str:
    title = sanitize(title.strip())[: WIDTH - 4]
    pad = WIDTH - len(title) - 2
    left = pad // 2
    return "-" * left + " " + title + " " + "-" * (pad - left)


def fmt_tokens(n: float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


# ── Transcript accounting ─────────────────────────────────────────


def _iter_usage(path: str):
    """Yield (model, usage-dict) for every assistant entry in a JSONL
    transcript. Tolerates malformed lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                msg = entry.get("message") or {}
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    yield str(msg.get("model", "")), usage
    except OSError:
        return


def _totals(pairs) -> dict:
    t = {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0, "model": "", "cost": 0.0}
    for model, u in pairs:
        i = int(u.get("input_tokens") or 0)
        o = int(u.get("output_tokens") or 0)
        cr = int(u.get("cache_read_input_tokens") or 0)
        cw = int(u.get("cache_creation_input_tokens") or 0)
        t["in"] += i
        t["out"] += o
        t["cache_r"] += cr
        t["cache_w"] += cw
        if model:
            t["model"] = model
        pi, po = _DEFAULT_PRICE
        for key, price in _PRICING:
            if key in model:
                pi, po = price
                break
        t["cost"] += (i * pi + o * po + cr * pi * 0.1 + cw * pi * 1.25) / 1e6
    return t


def _today_files() -> list[str]:
    """All project transcripts modified since local midnight."""
    midnight = _dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    root = Path.home() / ".claude" / "projects"
    files: list[str] = []
    if root.is_dir():
        for p in root.glob("*/*.jsonl"):
            try:
                if p.stat().st_mtime >= midnight:
                    files.append(str(p))
            except OSError:
                continue
    return files


def _last_context(path: str) -> tuple[int, int]:
    """(context_tokens, last_output_tokens) from the newest usage entry."""
    last = None
    for _model, u in _iter_usage(path):
        last = u
    if not last:
        return 0, 0
    ctx = (
        int(last.get("input_tokens") or 0)
        + int(last.get("cache_read_input_tokens") or 0)
        + int(last.get("cache_creation_input_tokens") or 0)
    )
    return ctx, int(last.get("output_tokens") or 0)


def _short_model(model: str) -> str:
    return model.replace("claude-", "")[: WIDTH - 7]


# ── Views ─────────────────────────────────────────────────────────


def _bar(pct: float) -> str:
    bar_w = WIDTH - 2
    filled = max(0, min(bar_w, round(bar_w * pct / 100)))
    return "[" + "#" * filled + "." * (bar_w - filled) + "]"


_LIMIT_LABELS = {
    "session": "Session (5h)",
    "weekly_all": "Week (all)",
    "weekly_scoped": "Week",
}


def _plan_usage() -> list[str]:
    """Plan limits as shown by the real /usage screen, from the same OAuth
    usage endpoint Claude Code uses (the user's own local credentials)."""
    import urllib.request

    cred = Path.home() / ".claude" / ".credentials.json"
    try:
        token = json.loads(cred.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
    except Exception:
        return []
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return []
    lines: list[str] = []
    for lim in data.get("limits") or []:
        pct = lim.get("percent")
        if pct is None:
            continue
        label = _LIMIT_LABELS.get(str(lim.get("kind")), str(lim.get("kind")))
        scope = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        if scope:
            label = f"{label} ({scope})"
        lines.append(f"{label}: {round(float(pct))}%")
        lines.append(_bar(float(pct)))
        resets = lim.get("resets_at")
        if resets:
            try:
                dt = _dt.datetime.fromisoformat(
                    str(resets).replace("Z", "+00:00")
                ).astimezone()
                lines.append(" resets " + dt.strftime("%a %H:%M"))
            except Exception:
                pass
    return lines


def _view_usage(info: dict) -> list[str]:
    lines = _plan_usage()
    if not lines:
        lines = ["(plan limits offline)"]
    tp = info.get("transcript_path", "")
    if tp and os.path.isfile(tp):
        s = _totals(_iter_usage(tp))
        lines += [
            "",
            "This session:",
            f" in {fmt_tokens(s['in'])}  out {fmt_tokens(s['out'])}",
        ]
        if s["model"]:
            lines.append(" model " + _short_model(s["model"]))
    today = _totals(u for f in _today_files() for u in _iter_usage(f))
    lines += [
        "Today (local):",
        f" in {fmt_tokens(today['in'])}  out {fmt_tokens(today['out'])}",
    ]
    return lines


def _view_context(info: dict) -> list[str]:
    tp = info.get("transcript_path", "")
    if not tp or not os.path.isfile(tp):
        return ["No active transcript.", "Send a prompt first."]
    ctx, out = _last_context(tp)
    if ctx == 0:
        return ["No usage entries yet."]
    limit = 200_000
    pct = min(999, round(100 * ctx / limit))
    return [
        f"Context: {fmt_tokens(ctx)} tok",
        f"~{pct}% of {fmt_tokens(limit)}",
        _bar(min(100.0, 100.0 * ctx / limit)),
        f"Last output: {fmt_tokens(out)}",
    ]


def _view_cost(info: dict) -> list[str]:
    lines: list[str] = []
    tp = info.get("transcript_path", "")
    if tp and os.path.isfile(tp):
        s = _totals(_iter_usage(tp))
        lines += [f"Session: ${s['cost']:.2f} est"]
        if s["model"]:
            lines.append(" model " + _short_model(s["model"]))
    else:
        lines.append("Session: no data yet")
    today = _totals(u for f in _today_files() for u in _iter_usage(f))
    lines += [
        f"Today:   ${today['cost']:.2f} est",
        "",
        "API list prices; sub-",
        "scription plans differ.",
    ]
    return lines


def _view_status(info: dict) -> list[str]:
    up = int(info.get("uptime_s", 0))
    h, rem = divmod(up, 3600)
    m, s = divmod(rem, 60)
    uptime = f"{h}h{m:02d}m" if h else (f"{m}m{s:02d}s" if m else f"{s}s")
    transport = str(info.get("transport", "?")).replace("Transport", "") or "?"
    proj = os.path.basename(str(info.get("project_dir", "")).rstrip("\\/")) or "?"
    return [
        f"Transport: {transport}",
        f"Flipper: {'connected' if info.get('flipper_connected') else 'offline'}",
        f"Claude: {'connected' if info.get('claude_connected') else 'no session'}",
        f"Project: {proj[:WIDTH - 9]}",
        f"Bridge up: {uptime}",
    ]


def _view_stats(info: dict) -> list[str]:
    try:
        with open(_STATS_FILE, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except Exception:
        stats = {}
    if not stats:
        return ["No tool calls yet", "this turn."]
    lines = ["Tools this turn:"]
    for name, count in sorted(stats.items(), key=lambda x: -x[1])[:10]:
        lines.append(f" {count:>3}x {sanitize(str(name))[: WIDTH - 6]}")
    return lines


_VIEWS = {
    "/usage": _view_usage,
    "/context": _view_context,
    "/cost": _view_cost,
    "/status": _view_status,
    "/stats": _view_stats,
}


def render(cmd: str, info: dict) -> tuple[str, list[str]]:
    """Return (title, lines) for a VIEW_COMMANDS slash command."""
    fn = _VIEWS[cmd]
    lines = [sanitize(l)[: WIDTH + 8] for l in fn(info)]
    return cmd, lines
