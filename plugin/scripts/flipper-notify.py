#!/usr/bin/env python3
"""CLI for the flipper-notify skill: send a custom notification to the Flipper.

Usage:
    python flipper-notify.py <sound> <vibro> [title] [subtitle]
    python flipper-notify.py success true "Done" "Tests passed"
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flipper_ipc  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    sound = argv[1]
    vibro = argv[2].strip().lower() in ("true", "1", "yes", "on")
    text = argv[3] if len(argv) > 3 else ""
    subtext = argv[4] if len(argv) > 4 else ""

    if not flipper_ipc.bridge_available():
        # Match upstream nc behaviour: exit silently when the bridge is down.
        return 0

    flipper_ipc.notify(sound, vibro, text, subtext)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
