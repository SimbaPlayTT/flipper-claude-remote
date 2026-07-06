"""Low-level Windows keyboard injection and window focusing (ctypes, no deps).

Used by WindowsInputBackend (input.py) and WindowsDictationBackend (voice.py).
Everything here is synchronous but effectively instant, except focus_hwnd()
which polls briefly and should be called from a worker thread.
"""

import ctypes
import logging
import sys
import time
from ctypes import wintypes

log = logging.getLogger(__name__)

if sys.platform != "win32":  # pragma: no cover - module is Windows-only
    raise ImportError("bridge.winput is only available on Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------------------
# Virtual-key codes
# ---------------------------------------------------------------------------

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22  # Page Down
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_LWIN = 0x5B

# Letters map to their uppercase ASCII codes ('C' -> 0x43 etc.)
def vk_for_char(ch: str) -> int:
    return ord(ch.upper())


# Keys on the extended part of the keyboard need KEYEVENTF_EXTENDEDKEY so
# console apps see the navigation key rather than a numpad key.
_EXTENDED_KEYS = {VK_PRIOR, VK_NEXT, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN, VK_LWIN}

# ---------------------------------------------------------------------------
# SendInput plumbing
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    # Unused, but required so the INPUT union has the size Windows expects.
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _key_event(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in _EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def _unicode_event(code_unit: int, up: bool) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def _send(events: list[INPUT], context: str) -> None:
    if not events:
        return
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        log.warning(
            "%s: SendInput injected %d/%d events (error=%d) — is the target "
            "window running elevated while the bridge is not?",
            context, sent, len(events), ctypes.get_last_error(),
        )


def send_vk(vk: int, modifiers: tuple[int, ...] = (), context: str = "key") -> None:
    """Press modifier(s) + key, then release in reverse order."""
    events: list[INPUT] = []
    for mod in modifiers:
        events.append(_key_event(mod, up=False))
    events.append(_key_event(vk, up=False))
    events.append(_key_event(vk, up=True))
    for mod in reversed(modifiers):
        events.append(_key_event(mod, up=True))
    _send(events, context)


def send_key_down(vk: int, context: str = "key_down") -> None:
    _send([_key_event(vk, up=False)], context)


def send_key_up(vk: int, context: str = "key_up") -> None:
    _send([_key_event(vk, up=True)], context)


def send_unicode(text: str, context: str = "type") -> None:
    """Type arbitrary text using KEYEVENTF_UNICODE (layout-independent)."""
    events: list[INPUT] = []
    for ch in text:
        if ch in ("\n", "\r"):
            events.append(_key_event(VK_RETURN, up=False))
            events.append(_key_event(VK_RETURN, up=True))
            continue
        # Characters outside the BMP need a UTF-16 surrogate pair.
        utf16 = ch.encode("utf-16-le")
        for i in range(0, len(utf16), 2):
            code_unit = int.from_bytes(utf16[i : i + 2], "little")
            events.append(_unicode_event(code_unit, up=False))
            events.append(_unicode_event(code_unit, up=True))
    _send(events, context)


# ---------------------------------------------------------------------------
# Window focusing
# ---------------------------------------------------------------------------

SW_RESTORE = 9


def focus_hwnd(hwnd: int, timeout: float = 1.0) -> bool:
    """Bring *hwnd* to the foreground; returns True when it got focus.

    Windows refuses SetForegroundWindow for processes that haven't received
    recent input; injecting a no-op Alt press first makes this process the
    last-input owner so the call is honoured (same trick as on macOS/Linux
    ports of this problem).
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        if user32.GetForegroundWindow() == hwnd:
            return True
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.10)
        send_key_down(VK_MENU, "focus_alt")
        try:
            user32.SetForegroundWindow(hwnd)
        finally:
            send_key_up(VK_MENU, "focus_alt")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if user32.GetForegroundWindow() == hwnd:
                time.sleep(0.05)  # let the window settle before typing
                return True
            time.sleep(0.02)
        log.warning("focus: window %#x did not reach the foreground", hwnd)
        return False
    except Exception as e:
        log.error("focus error: %s", e)
        return False


def get_console_window() -> int:
    return int(kernel32.GetConsoleWindow())


def get_foreground_window() -> int:
    return int(user32.GetForegroundWindow())


def is_window_visible(hwnd: int) -> bool:
    return bool(user32.IsWindowVisible(hwnd))
