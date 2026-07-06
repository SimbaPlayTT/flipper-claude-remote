#!/usr/bin/env python3
"""StopFailure hook: notify Flipper when a turn ends with an API error."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0
    flipper_ipc.notify("error", True, "Claude", "API Error")
    return 0


if __name__ == "__main__":
    sys.exit(main())
