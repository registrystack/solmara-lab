#!/usr/bin/env python3
"""Validate image pin conventions for the lab."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE_RE = re.compile(r"^([A-Z0-9_]+)=([^#\s]+)$")
PIN_RE = re.compile(r"^[^#\s]+@sha256:[0-9a-f]{64}$")
REGISTRY_STACK_IMAGE_KEYS = {"REGISTRY_RELAY_IMAGE", "REGISTRY_NOTARY_IMAGE"}


def main() -> int:
    versions = ROOT / "versions.env"
    if not versions.exists():
        print("versions.env is missing", file=sys.stderr)
        return 1

    failures: list[str] = []
    for line_no, raw in enumerate(versions.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            failures.append(f"versions.env:{line_no}: expected NAME=image")
            continue
        key, value = match.groups()
        if key in REGISTRY_STACK_IMAGE_KEYS and not PIN_RE.match(value):
            failures.append(f"versions.env:{line_no}: {key} must use image@sha256:<64 hex>")
        if "@latest" in value or ":latest" in value:
            failures.append(f"versions.env:{line_no}: latest tags are not allowed")

    for compose in [ROOT / "compose.yaml", ROOT / "compose.hosted.yaml"]:
        if not compose.exists():
            continue
        text = compose.read_text()
        if "@latest" in text or ":latest" in text:
            failures.append(f"{compose.name}: latest tags are not allowed")
        if compose.name == "compose.yaml" and (
            "REGISTRY_RELAY_IMAGE" not in text or "REGISTRY_NOTARY_IMAGE" not in text
        ):
            failures.append(f"{compose.name}: expected Registry Stack image env references")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
