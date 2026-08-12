#!/usr/bin/env python3
"""Fail closed when the active deployment regresses to retired topology."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = [
    ROOT / "compose.yaml",
    ROOT / "compose.hosted.yaml",
    ROOT / "compose.esignet.yaml",
    ROOT / "justfile",
    ROOT / "config/evidence/Caddyfile",
    ROOT / "config/walt/Caddyfile",
    ROOT / "config/walt/README.md",
    ROOT / "config/walt/registration-defaults.conf",
    *sorted(ROOT.glob("compose.coolify*.yaml")),
]
FORBIDDEN = {
    "retired database": re.compile(r"(?i)\bpostgres(?:ql)?\b"),
    "retired workload agent": re.compile(r"(?i)workload[-_ ](?:identity[-_ ])?agent"),
    "retired Notary": re.compile(r"(?i)\bnotary\b"),
    "retired data-purpose": re.compile(r"(?i)data[-_]purpose"),
    "retired authoring CLI": re.compile(r"\bregistryctl\b"),
    "retired dataset route": re.compile(r"/v1/datasets\b"),
}


def failures(paths: list[Path] = ACTIVE) -> list[str]:
    found: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        # eSignet is the only surviving stateful third-party component. Its
        # database is deliberately isolated from Registry Stack runtime state.
        suppress_database = path.name in {"compose.esignet.yaml", "compose.coolify.esignet.yaml"}
        for label, pattern in FORBIDDEN.items():
            if suppress_database and label == "retired database":
                continue
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                found.append(f"{path.name}:{line}: {label}")
    return found


def main() -> int:
    found = failures()
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
