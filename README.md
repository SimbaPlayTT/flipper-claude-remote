# flipper-claude-remote

**Claude Buddy for Windows** — a Windows-capable port of [jxw1102/flipper-claude-buddy](https://github.com/jxw1102/flipper-claude-buddy) (MIT), which turns a Flipper Zero into a physical remote control and status display for **Claude Code**.

The Flipper app (`.fap`) is the **unmodified upstream Claude Buddy app** — same UI, same screens, same sounds, 1:1. All Windows work lives on the host side: the Python bridge daemon and the Claude Code plugin hooks were ported so the whole system runs on Windows (upstream supports macOS/Linux only).

```
Flipper Zero (claude_buddy.fap — vendored upstream, UI 1:1)
  ↕ USB CDC serial  OR  BLE serial (JSON lines protocol)
Host bridge (Python asyncio daemon)
  ↕ Unix socket (macOS/Linux)  OR  loopback TCP + port file (Windows)
Claude Code hook scripts (plugin/, all Python — no bash required)
```

## What the Windows port changes

| Area | Upstream (macOS/Linux) | This port (Windows) |
|---|---|---|
| Keystroke forwarding | AppleScript / xdotool | `SendInput` via ctypes (no extra deps) |
| Window targeting | Terminal tab / X11 `WINDOWID` | Terminal HWND captured at each prompt |
| Hooks ⇄ bridge IPC | Unix socket `/tmp/…sock` | TCP on `127.0.0.1`, port published in `%TEMP%\claude-flipper-bridge.port` |
| USB port detection | `/dev/cu.usbmodem*` / `/dev/ttyACM*` | COM ports by USB VID:PID `0483:5740` |
| Voice dictation | macOS native dictation | Windows voice typing (**Win+H**) |
| Hook scripts | bash + python3 | Python only (`python` on PATH) |
| Daemon stop | `kill $PID` | `shutdown` IPC action (clean BLE disconnect), kill as fallback |
| BLE transport | bleak | bleak (unchanged — cross-platform) |

Everything else — protocol, daemon logic, permission flow, sounds, menu system — is upstream code, kept as close to verbatim as possible so future upstream updates merge easily.

## Repository structure

```
flipper-claude-remote/
├── README.md
├── LICENSE                    # this repo (MIT)
├── LICENSE.upstream           # upstream Claude Buddy license (MIT, © 2026 jxw1102)
├── .claude-plugin/
│   └── marketplace.json       # lets `claude plugin marketplace add` work on this repo
├── flipper/
│   └── claude_buddy/          # vendored upstream Flipper app (FAP) — unmodified
│       ├── application.fam
│       ├── claude_buddy.c     # entry point, GUI event loop, message dispatch
│       ├── ui.c / ui.h        # display rendering, button handlers (the 1:1 UI)
│       ├── transport_bt.c / serial.c / transport_nus.c   # BLE / USB / Desktop-mode
│       ├── protocol.* nus_*.* app_settings.* notifications.*
│       └── icons/ screenshots/
└── plugin/                    # Claude Code plugin (Windows-capable port)
    ├── .claude-plugin/plugin.json
    ├── hooks/hooks.json       # all hooks invoke python scripts
    ├── host-bridge/           # bridge daemon (pip package)
    │   ├── pyproject.toml     # deps: bleak, pyserial, pyserial-asyncio
    │   └── bridge/
    │       ├── daemon.py claude_ipc.py serial_conn.py protocol.py config.py
    │       ├── transport_usb.py transport_bt.py transport_auto.py transport.py
    │       ├── input.py       # + WindowsInputBackend (SendInput)
    │       ├── winput.py      # NEW: ctypes SendInput + window focus (Windows)
    │       └── voice.py       # + Windows voice typing backend (Win+H)
    ├── scripts/               # hook scripts (all Python)
    │   ├── flipper_ipc.py     # NEW: shared client — Unix socket or TCP port file
    │   ├── session_target.py  # terminal window detection (incl. Windows HWND)
    │   ├── on-session-start.py  on-session-end.py  on-stop.py  on-prompt-submit.py
    │   ├── on-permission-request.py  on-post-tool-use.py  … (one per hook event)
    │   └── flipper-notify.py  # CLI used by the flipper-notify skill
    └── skills/notify/SKILL.md
```

## Requirements

- **Flipper Zero** — official or Momentum firmware. The `.fap` here was built and verified against official SDK **1.4.3** (f7, API 87.1) and runs on Momentum mntm-012.
- **Windows 10/11** with Bluetooth LE (for BLE) and/or a USB cable.
- **Python 3.10+ on PATH as `python`** (hooks and bridge bootstrap use it).
- [`ufbt`](https://github.com/flipperdevices/flipperzero-ufbt) if you want to build the app yourself (`pip install ufbt`).

## Setup

### 1. Install the Flipper app

```powershell
cd flipper\claude_buddy
ufbt          # build only → dist\claude_buddy.fap
ufbt launch   # or: build + install + run on a USB-connected Flipper
```

Alternatively copy `dist\claude_buddy.fap` to the SD card at `SD Card/apps/Bluetooth/` with qFlipper. (Upstream also publishes it on the Flipper app catalog as "Claude Buddy".)

### 2. Install the Claude Code plugin

From a local clone:

```text
claude plugin marketplace add C:\path\to\flipper-claude-remote
claude plugin install flipper-claude-buddy@flipper-claude-remote
```

(or `claude plugin marketplace add <youruser>/flipper-claude-remote` once pushed to GitHub).

When asked, set **transport** to `auto` (default), `usb`, or `ble`. The bridge daemon starts automatically with every Claude Code session (first start creates a private venv and installs its own dependencies — takes ~30 s once) and stops when the last session ends.

### 3. Launch Claude Buddy on the Flipper

**Apps → Bluetooth → Claude Buddy**. You'll hear the startup fanfare when the connection is established.

## Buttons (unchanged from upstream)

| Button | Action |
|--------|--------|
| UP | Start / stop voice dictation (Windows voice typing, Win+H) |
| UP (hold) | Hold Space for voice input |
| LEFT | Interrupt Claude (Esc) |
| LEFT (hold) | Send Ctrl+C |
| RIGHT | Open slash command menu |
| RIGHT (hold) | Open menu |
| OK | Submit Enter (⏎) |
| OK (hold) | Type "yes" and submit |
| DOWN | Send Down arrow (↓) |
| DOWN (hold) | Toggle mute |
| BACK | Send Backspace (⌫) |
| BACK (hold) | Exit |

The on-device menu, status display, transcript view, permission prompts (Allow / Deny on the Flipper), and Claude Desktop (BLE) mode all work exactly as upstream — same code.

## Windows connection notes

**USB** — plug the Flipper in *before* starting the app. The app claims the USB serial channel only when it detects a cable via the charge state; if your Flipper runs Momentum with a **charge cap** enabled, the cable is not detected (not charging + not "charging done") and the app falls back to BLE. Either disable the charge cap, or just use BLE.

**BLE** — Bluetooth must be ON in the Flipper's **Settings → Bluetooth** *and* on the PC. On the first connection Windows and the Flipper will show a pairing confirmation — accept both. The bridge scans for the Flipper's advertised service UUID, so a renamed Flipper is still found; you can pin it with the plugin's `bluetoothName` option or `FLIPPER_BT_NAME`.

**Keystroke targeting** — the bridge captures your terminal's window handle every time you submit a prompt and refocuses that window before injecting keys. If the terminal runs **as Administrator** and the bridge doesn't, Windows silently blocks injected input (the bridge log then shows `SendInput injected 0/…`) — run both at the same privilege level.

**Voice (UP button)** — triggers Windows voice typing (Win+H), which requires online speech recognition to be enabled (Settings → Privacy & security → Speech). ESC (LEFT button) or UP again dismisses it. A different dictation tool can be wired in with `FLIPPER_DICTATION_BACKEND=custom` + `FLIPPER_DICTATION_START_CMD`.

**Runtime files** (for debugging) — `%TEMP%\claude-flipper-bridge.log`, `.port`, `.pid`, `.refcount`. Tail the log with:

```powershell
Get-Content $env:TEMP\claude-flipper-bridge.log -Wait -Tail 50
```

Run the bridge manually (without Claude Code) for testing:

```powershell
cd plugin\host-bridge
pip install -e .
python -m bridge --transport ble --log-level debug
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Flipper not found over USB | Make sure the Claude Buddy app is running on the Flipper and no other program (qFlipper, a serial monitor, `ufbt cli`) holds the COM port. Pin the port with the plugin's `serial_port` option (e.g. `COM6`). |
| Bridge connects to the Flipper **CLI** instead of the app (log shows the Flipper ASCII banner) | The app didn't claim USB — it's in BLE mode (see the charge-cap note above). Use BLE, or disable the charge cap and restart the app. |
| Flipper not found over BLE | Bluetooth ON on both sides, Claude Buddy app open on the Flipper. If it used to work, remove the Flipper from Windows *Settings → Bluetooth & devices* and re-pair. |
| Buttons do nothing | Check `%TEMP%\claude-flipper-bridge.log`. `SendInput injected 0/…` → elevation mismatch (see above). No log lines at all → bridge not running; start a new Claude Code session. |
| No sound on task complete | The bridge is not running or the Flipper is disconnected — check the log. |
| Hook errors mentioning `python` | Python 3.10+ must be on PATH as `python` (`python --version` in a fresh terminal). |

## Credits & license

- **Claude Buddy** (Flipper app, bridge architecture, protocol, plugin) — © 2026 [jxw1102](https://github.com/jxw1102/flipper-claude-buddy), MIT ([LICENSE.upstream](LICENSE.upstream)). The Flipper app is vendored unmodified; if you enjoy it, consider [supporting the original author](https://ko-fi.com/jxw1102).
- **Windows port** (winput.py, WindowsInputBackend, Windows dictation backend, TCP IPC, COM-port detection, Python hook rewrites) — MIT ([LICENSE](LICENSE)).
