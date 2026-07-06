#!/usr/bin/env python3
"""TaskCompleted hook: buzz Flipper when a task is marked done."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0
    flipper_ipc.notify("success", True, "Task", "Completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
