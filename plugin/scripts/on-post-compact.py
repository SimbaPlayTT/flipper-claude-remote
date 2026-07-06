#!/usr/bin/env python3
"""PostCompact hook: stop cyan LED blink on Flipper after context compaction finishes."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main() -> int:
    if not flipper_ipc.bridge_available():
        return 0
    flipper_ipc.notify("compact_done", False, "Compacted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
