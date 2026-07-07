"""JSON protocol for Flipper <-> Host Bridge communication."""

import json
import time
import uuid

def make_id() -> str:
    return uuid.uuid4().hex[:8]


def encode(msg_type: str, data: dict | None = None) -> bytes:
    msg = {
        "v": 1,
        "t": msg_type,
        "d": data or {},
    }
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def decode(line: bytes) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        # A corrupted BLE chunk must parse-fail (warning), not raise a
        # UnicodeDecodeError that the read loop treats as a link failure.
        msg = json.loads(line.decode("utf-8", errors="replace"))
        if isinstance(msg, dict) and "t" in msg:
            return msg
    except json.JSONDecodeError:
        pass
    return None


def notify_msg(sound: str, vibro: bool = True, text: str = "", subtext: str = "") -> bytes:
    d: dict = {"sound": sound, "vibro": vibro, "text": text}
    if subtext:
        d["sub"] = subtext[:21]
    return encode("notify", d)


def state_msg(claude_connected: bool = False) -> bytes:
    return encode("state", {"claude": claude_connected})


def status_msg(line1: str, line2: str = "") -> bytes:
    d: dict = {"line1": line1[:21]}
    if line2:
        d["line2"] = line2[:21]
    return encode("status", d)


def ping_msg(rssi: int | None = None) -> bytes:
    d: dict[str, int] = {}
    if rssi is not None:
        d["rssi"] = int(rssi)
    return encode("ping", d)


def menu_msg(items: list[str]) -> bytes:
    return encode("menu", {"items": "|".join(items)})


def term_msg(lines: list[str], clr: bool = False, show: bool = False) -> bytes:
    """Terminal-view lines for the Flipper. Lines must already be sanitized
    (ASCII, no '|', '"' or '\\') and wrapped to the Flipper's line width —
    the on-device JSON parser does no unescaping."""
    d: dict = {"lines": "|".join(lines)}
    if clr:
        d["clr"] = True
    if show:
        d["show"] = True
    return encode("term", d)


def pick_msg(title: str, items: list[str]) -> bytes:
    """Option picker for a multi-choice question. Items must be sanitized
    like term lines (ASCII, no '|', '\"' or '\\\\')."""
    return encode("pick", {"title": title[:21], "items": "|".join(items)})


def perm_msg(tool: str, detail: str = "") -> bytes:
    d: dict = {"tool": tool[:21]}
    if detail:
        d["detail"] = detail[:21]
    return encode("perm", d)
