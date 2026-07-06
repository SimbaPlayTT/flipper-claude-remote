"""Shared IPC client for the Claude Buddy hook scripts.

Connects to the host-bridge daemon over a Unix domain socket on POSIX or a
loopback TCP port on Windows (published by the daemon in a port file).
Stdlib only — hook scripts run with the system Python, not the bridge venv.
"""

from __future__ import annotations

import ctypes
import json
import os
import socket
import sys
import tempfile

IS_WINDOWS = sys.platform == "win32"

RUNTIME_DIR = tempfile.gettempdir() if IS_WINDOWS else "/tmp"

SOCKET_PATH = os.environ.get(
    "FLIPPER_BRIDGE_SOCKET", os.path.join(RUNTIME_DIR, "claude-flipper-bridge.sock")
)
PORT_FILE = os.environ.get(
    "FLIPPER_BRIDGE_PORT_FILE", os.path.join(RUNTIME_DIR, "claude-flipper-bridge.port")
)
PID_FILE = os.path.join(RUNTIME_DIR, "claude-flipper-bridge.pid")
LOG_FILE = os.path.join(RUNTIME_DIR, "claude-flipper-bridge.log")
REFCOUNT_FILE = os.path.join(RUNTIME_DIR, "claude-flipper-bridge.refcount")
STATS_FILE = os.path.join(RUNTIME_DIR, "claude-flipper-turn-stats.json")
SKIP_STOP_FLAG = os.path.join(RUNTIME_DIR, "claude-flipper-skip-stop.flag")


def bridge_available() -> bool:
    """Cheap liveness check: is the IPC endpoint published?"""
    if IS_WINDOWS:
        return os.path.isfile(PORT_FILE)
    return os.path.exists(SOCKET_PATH)


def _connect(timeout: float) -> socket.socket:
    if IS_WINDOWS:
        with open(PORT_FILE, "r", encoding="utf-8") as f:
            info = json.load(f)
        return socket.create_connection(("127.0.0.1", int(info["port"])), timeout=timeout)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCKET_PATH)
    return s


def send_request(payload: dict, timeout: float = 10.0) -> dict | None:
    """Send one JSON request and return the parsed response (None on error)."""
    try:
        s = _connect(timeout)
        try:
            s.sendall(json.dumps(payload).encode())
            s.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
        finally:
            s.close()
        raw = b"".join(chunks).strip()
        return json.loads(raw.decode()) if raw else None
    except Exception:
        return None


def notify(sound: str, vibro: bool, text: str, subtext: str = "") -> dict | None:
    return send_request(
        {"action": "notify", "sound": sound, "vibro": vibro, "text": text, "subtext": subtext}
    )


def display(text: str, subtext: str = "") -> dict | None:
    return send_request({"action": "display", "text": text, "subtext": subtext})


# ---------------------------------------------------------------------------
# Process helpers shared by the session-start / session-end hooks
# ---------------------------------------------------------------------------

def read_pid() -> int | None:
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        # NOTE: os.kill(pid, 0) TERMINATES the process on Windows — never use
        # it as a liveness probe. Query the process handle instead.
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def kill_pid(pid: int) -> None:
    """Forcefully terminate the bridge process (last resort — prefer the
    'shutdown' IPC action so the daemon can disconnect BLE cleanly)."""
    if pid <= 0:
        return
    if IS_WINDOWS:
        PROCESS_TERMINATE = 0x0001
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            try:
                kernel32.TerminateProcess(handle, 1)
            finally:
                kernel32.CloseHandle(handle)
        return
    import signal as _signal

    try:
        os.kill(pid, _signal.SIGTERM)
    except OSError:
        pass


def remove_quiet(*paths: str) -> None:
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass
