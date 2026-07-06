#!/usr/bin/env python3
"""PreCompact hook: start cyan LED blink on Flipper while context is being compacted."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0
    flipper_ipc.notify("led_compact", False, "Compacting...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
