#!/usr/bin/env python3
"""Detect and register the current Claude runner target with the bridge.

Importable module (used by other hooks) and CLI:
    python session_target.py register_target
    python session_target.py release_target
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


TERM_PROGRAM_APP_NAMES = {
    # macOS terminals
    "Apple_Terminal": "Terminal",
    "Terminal": "Terminal",
    "Terminal.app": "Terminal",
    "iTerm.app": "iTerm",
    "iTerm2": "iTerm",
    # cross-platform
    "vscode": "Visual Studio Code",
    "WarpTerminal": "Warp",
    "WezTerm": "WezTerm",
    "Hyper": "Hyper",
    "Ghostty": "Ghostty",
    # Linux terminals
    "gnome-terminal": "GNOME Terminal",
    "konsole": "Konsole",
    "xterm": "XTerm",
    "alacritty": "Alacritty",
    "kitty": "kitty",
    "tilix": "Tilix",
    "xfce4-terminal": "Xfce Terminal",
}


def _normalize_tty(value: str) -> str:
    value = (value or "").strip()
    if not value or value == "??":
        return ""
    if value.startswith("/dev/"):
        return value
    return f"/dev/{value}"


def detect_tty() -> str:
    if sys.platform == "win32":
        return ""

    for fd in (0, 1, 2):
        try:
            return _normalize_tty(os.ttyname(fd))
        except OSError:
            pass

    pid = os.getpid()
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        try:
            ppid = subprocess.check_output(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            tty = subprocess.check_output(
                ["ps", "-o", "tty=", "-p", str(pid)],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception:
            break

        normalized_tty = _normalize_tty(tty)
        if normalized_tty:
            return normalized_tty

        try:
            pid = int(ppid)
        except ValueError:
            break

    return ""


def _detect_windows_hwnd() -> str:
    """Best-available HWND of the terminal hosting this Claude session.

    Prefer the process's own console window (classic conhost). Under
    Windows Terminal / ConPTY that window is hidden, so fall back to the
    current foreground window — hooks fire right after user interaction, so
    the foreground window is almost always the hosting terminal.
    """
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
            return str(hwnd)
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return str(hwnd) if hwnd else ""
    except Exception:
        return ""


def _detect_windows_app_name(term_program: str) -> str:
    if term_program:
        return TERM_PROGRAM_APP_NAMES.get(term_program, term_program)
    if os.environ.get("WT_SESSION"):
        return "Windows Terminal"
    return ""


def build_target() -> dict[str, str]:
    term_program = (os.environ.get("TERM_PROGRAM") or "").strip()

    if sys.platform == "win32":
        target = {
            "app_name": _detect_windows_app_name(term_program),
            "term_program": term_program,
            "term_session_id": (
                os.environ.get("WT_SESSION") or os.environ.get("TERM_SESSION_ID") or ""
            ).strip(),
            "iterm_session_id": "",
            "tty": "",
            "window_id": _detect_windows_hwnd(),
        }
    else:
        target = {
            "app_name": TERM_PROGRAM_APP_NAMES.get(term_program, term_program),
            "term_program": term_program,
            "term_session_id": (os.environ.get("TERM_SESSION_ID") or "").strip(),
            "iterm_session_id": (os.environ.get("ITERM_SESSION_ID") or "").strip(),
            "tty": detect_tty(),
            # X11 window ID — set by VTE-based terminals (gnome-terminal, kitty,
            # etc.). Used by XdotoolInputBackend on Linux to focus the window.
            "window_id": (os.environ.get("WINDOWID") or "").strip(),
        }

    material = json.dumps(target, sort_keys=True, separators=(",", ":")).encode()
    target["session_key"] = hashlib.sha1(material).hexdigest()[:16]
    return target


def send_action(action: str, target: dict[str, str]) -> int:
    response = flipper_ipc.send_request({"action": action, **target})
    return 0 if response is not None else 1


def register_current_session(action: str = "register_target") -> int:
    if not flipper_ipc.bridge_available():
        return 0
    target = build_target()
    if not any(
        (
            target["app_name"],
            target["tty"],
            target["term_session_id"],
            target["iterm_session_id"],
            target["window_id"],
        )
    ):
        return 0
    return send_action(action, target)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"register_target", "release_target"}:
        print(
            "usage: session_target.py <register_target|release_target>",
            file=sys.stderr,
        )
        return 2
    return register_current_session(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
