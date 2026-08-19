#!/usr/bin/env python3
"""Require all external local Transit proxies before starting runtimes."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("mint", "cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")


def failures(root: Path = ROOT) -> list[str]:
    result = []
    for provider in PROVIDERS:
        socket = root / "config/evidence/local/cells" / provider / "transit/transit-proxy.sock"
        try:
            mode = socket.stat().st_mode
        except FileNotFoundError:
            result.append(f"{provider}: Transit proxy socket is missing")
            continue
        if not stat.S_ISSOCK(mode):
            result.append(f"{provider}: Transit provider path is not a Unix socket")
    return result


def main() -> int:
    found = failures()
    if found:
        print("\n".join(found), file=sys.stderr)
        print("Start the seven external signer providers; private keys are never mounted into Evidence or Mint.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
