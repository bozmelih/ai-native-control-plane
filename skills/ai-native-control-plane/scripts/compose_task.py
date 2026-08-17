#!/usr/bin/env python3
"""Compatibility entry point for V4 task preparation.

V3.1 composition requests remain readable, but every newly emitted task packet
uses the V4 lifecycle contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from control_plane import LifecycleError, load_json, prepare_task


CompositionError = LifecycleError


def compose(request: dict[str, Any]) -> dict[str, Any]:
    """Prepare a V4 task packet from a V4 or compatible V3.1 request."""

    return prepare_task(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path, help="V4 or compatible V3.1 request JSON")
    parser.add_argument("--output", type=Path, help="Optional V4 task-packet path")
    args = parser.parse_args()
    try:
        result = compose(load_json(args.request))
    except (OSError, json.JSONDecodeError, LifecycleError) as exc:
        print(f"ERROR ERR_PREPARE: {exc}")
        return 1
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
