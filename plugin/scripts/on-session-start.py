#!/usr/bin/env python3
"""SessionStart hook: ensure the bridge daemon is running, then notify Flipper.

Cross-platform port of the upstream shell hook: works on Windows (detached
process, venv Scripts\\, TCP IPC via port file) as well as macOS/Linux.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402
import session_target  # noqa: E402

SOURCES = {
    "startup": "New session",
    "resume": "Resumed",
    "clear": "After clear",
    "compact": "After compaction",
}

IS_WINDOWS = flipper_ipc.IS_WINDOWS


def read_subtext_from_payload() -> str:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return ""
    source = data.get("source") or ""
    label = SOURCES.get(source, "")
    if not label:
        label = (data.get("model") or "")[:21]
    return label


def source_hash(bridge_dir: Path) -> str:
    """md5 of pyproject.toml + all bridge/*.py — restart daemon when it changes."""
    md5 = hashlib.md5()
    files = [bridge_dir / "pyproject.toml"]
    files += sorted((bridge_dir / "bridge").glob("*.py"))
    for path in files:
        try:
            md5.update(path.read_bytes())
        except OSError:
            pass
    return md5.hexdigest()


def venv_python(venv_dir: Path) -> Path:
    if IS_WINDOWS:
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv(venv_dir: Path, marker: Path, current_hash: str, bridge_dir: Path) -> bool:
    installed = marker.read_text().strip() if marker.is_file() else ""
    if venv_dir.is_dir() and installed == current_hash and venv_python(venv_dir).is_file():
        return True
    print("[bridge] Setting up Python environment...", file=sys.stderr)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                str(venv_python(venv_dir)),
                "-m",
                "pip",
                "install",
                "-q",
                "--force-reinstall",
                str(bridge_dir),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip()
        print(f"[bridge] Python environment setup failed: {err[-400:]}", file=sys.stderr)
        return False
    marker.write_text(current_hash)
    return True


def spawn_daemon(python: Path, log_path: str, env: dict[str, str]) -> int:
    log_file = open(log_path, "a", encoding="utf-8", errors="replace")
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": log_file,
        "env": env,
        "close_fds": True,
    }
    if IS_WINDOWS:
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = (
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([str(python), "-m", "bridge"], **kwargs)
    log_file.close()
    return proc.pid


def stop_daemon(pid: int | None) -> None:
    """Ask the daemon to shut down cleanly; fall back to terminating it."""
    if flipper_ipc.bridge_available():
        flipper_ipc.send_request({"action": "shutdown"}, timeout=3.0)
        for _ in range(30):
            if pid is not None and not flipper_ipc.pid_alive(pid):
                break
            time.sleep(0.1)
    if pid is not None and flipper_ipc.pid_alive(pid):
        flipper_ipc.kill_pid(pid)
    flipper_ipc.remove_quiet(
        flipper_ipc.SOCKET_PATH,
        flipper_ipc.PORT_FILE,
        flipper_ipc.PID_FILE,
        flipper_ipc.REFCOUNT_FILE,
    )


def usb_port_present() -> bool:
    """Pre-check for USB-only mode. Returns True when unsure (attempt anyway)."""
    if IS_WINDOWS:
        try:
            from serial.tools import list_ports  # available only if pyserial installed

            return any(p.vid == 0x0483 and p.pid == 0x5740 for p in list_ports.comports())
        except Exception:
            return True
    import glob

    return bool(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))


def main() -> int:
    subtext = read_subtext_from_payload()

    plugin_root = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).parent.parent)
    plugin_data = Path(
        os.environ.get("CLAUDE_PLUGIN_DATA")
        or os.path.join(flipper_ipc.RUNTIME_DIR, "flipper-claude-buddy")
    )
    bridge_dir = plugin_root / "host-bridge"
    venv_dir = plugin_data / "venv"
    marker = venv_dir / ".installed-hash"
    current_hash = source_hash(bridge_dir)

    # Forward plugin userConfig options to bridge env vars
    env = dict(os.environ)
    if os.environ.get("CLAUDE_PLUGIN_OPTION_serial_port"):
        env["FLIPPER_SERIAL_PORT"] = os.environ["CLAUDE_PLUGIN_OPTION_serial_port"]
    if os.environ.get("CLAUDE_PLUGIN_OPTION_transport"):
        env["FLIPPER_TRANSPORT"] = os.environ["CLAUDE_PLUGIN_OPTION_transport"]
    bt_name_cache = plugin_data / "bt_name"
    if os.environ.get("CLAUDE_PLUGIN_OPTION_bluetoothName"):
        env["FLIPPER_BT_NAME"] = os.environ["CLAUDE_PLUGIN_OPTION_bluetoothName"]
    elif bt_name_cache.is_file():
        env["FLIPPER_BT_NAME"] = bt_name_cache.read_text().strip()
    env["FLIPPER_PLUGIN_DATA"] = str(plugin_data)
    env["FLIPPER_PROJECT_DIR"] = os.getcwd()

    # Skip if no Flipper is reachable (unless the bridge is already running)
    if not flipper_ipc.bridge_available():
        transport = env.get("FLIPPER_TRANSPORT", "auto")
        if env.get("FLIPPER_SERIAL_PORT"):
            if not IS_WINDOWS and not os.path.exists(env["FLIPPER_SERIAL_PORT"]):
                return 0
        elif transport == "usb" and not usb_port_present():
            return 0
        # "ble" or "auto": always attempt — BLE cannot be pre-checked cheaply

    # Clean up a stale or outdated bridge
    if flipper_ipc.bridge_available():
        pid = flipper_ipc.read_pid()
        installed_hash = marker.read_text().strip() if marker.is_file() else ""
        if pid is not None and flipper_ipc.pid_alive(pid):
            if installed_hash != current_hash:
                print(
                    f"[bridge] Bridge code changed; restarting daemon {pid}...",
                    file=sys.stderr,
                )
                stop_daemon(pid)
        elif pid is not None:
            print(f"[bridge] Cleaning up stale bridge (pid {pid} gone)...", file=sys.stderr)
            flipper_ipc.remove_quiet(
                flipper_ipc.SOCKET_PATH,
                flipper_ipc.PORT_FILE,
                flipper_ipc.PID_FILE,
                flipper_ipc.REFCOUNT_FILE,
            )
        elif flipper_ipc.send_request({}, timeout=1.0) is None:
            print("[bridge] Cleaning up orphaned IPC endpoint...", file=sys.stderr)
            flipper_ipc.remove_quiet(flipper_ipc.SOCKET_PATH, flipper_ipc.PORT_FILE)

    # Start bridge if not already running
    if not flipper_ipc.bridge_available():
        print("[bridge] Starting flipper bridge...", file=sys.stderr)
        if not ensure_venv(venv_dir, marker, current_hash, bridge_dir):
            return 0
        pid = spawn_daemon(venv_python(venv_dir), flipper_ipc.LOG_FILE, env)
        Path(flipper_ipc.PID_FILE).write_text(str(pid))
        for _ in range(30):
            if flipper_ipc.bridge_available():
                break
            time.sleep(0.1)
        # On Windows the venv python.exe is a launcher shim, so the Popen pid
        # is not the daemon's. The daemon publishes its real pid in the port
        # file — prefer that for liveness checks and termination.
        if IS_WINDOWS and os.path.isfile(flipper_ipc.PORT_FILE):
            try:
                with open(flipper_ipc.PORT_FILE, "r", encoding="utf-8") as f:
                    real_pid = int(json.load(f)["pid"])
                Path(flipper_ipc.PID_FILE).write_text(str(real_pid))
            except Exception:
                pass

    if not flipper_ipc.bridge_available():
        print(
            f"[bridge] IPC endpoint not available, bridge may have failed. "
            f"Check {flipper_ipc.LOG_FILE}",
            file=sys.stderr,
        )
        return 0

    # Register the current runner session before Claude connects so input
    # targeting is ready as soon as Flipper events arrive.
    try:
        session_target.register_current_session("register_target")
    except Exception:
        pass

    # Increment session reference counter
    try:
        count = int(Path(flipper_ipc.REFCOUNT_FILE).read_text().strip())
    except Exception:
        count = 0
    Path(flipper_ipc.REFCOUNT_FILE).write_text(str(count + 1))

    flipper_ipc.send_request({"action": "claude_connect", "project_dir": os.getcwd()})

    # Match the "Claude Code / Connected" notification shown when the Flipper
    # first connects to the bridge, so every new session gives the same cue.
    flipper_ipc.notify("connect", True, "Claude Code", subtext or "Connected")

    return 0


if __name__ == "__main__":
    sys.exit(main())
