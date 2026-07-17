#!/usr/bin/env python3
"""Validate image pin conventions for the lab."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE_RE = re.compile(r"^([A-Z0-9_]+)=([^#\s]+)$")
PIN_RE = re.compile(r"^[^#\s]+@sha256:[0-9a-f]{64}$")
REGISTRY_STACK_IMAGE_KEYS = {"REGISTRY_RELAY_IMAGE", "REGISTRY_NOTARY_IMAGE"}
COMPOSE_FALLBACK_RE = re.compile(
    r"\$\{(?P<key>REGISTRY_(?:RELAY|NOTARY)_IMAGE):-(?P<value>[^}]+)\}"
)


def main() -> int:
    versions = ROOT / "versions.env"
    if not versions.exists():
        print("versions.env is missing", file=sys.stderr)
        return 1

    failures: list[str] = []
    values: dict[str, str] = {}
    for line_no, raw in enumerate(versions.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            failures.append(f"versions.env:{line_no}: expected NAME=image")
            continue
        key, value = match.groups()
        values[key] = value
        if key in REGISTRY_STACK_IMAGE_KEYS and not PIN_RE.match(value):
            failures.append(f"versions.env:{line_no}: {key} must use image@sha256:<64 hex>")
        if "@latest" in value or ":latest" in value:
            failures.append(f"versions.env:{line_no}: latest tags are not allowed")

    for key in REGISTRY_STACK_IMAGE_KEYS:
        if key not in values:
            failures.append(f"versions.env: {key} is required")

    compose_files = [ROOT / "compose.yaml", ROOT / "compose.hosted.yaml"]
    compose_files.extend(sorted(ROOT.glob("compose.coolify*.yaml")))
    fallback_counts = {key: 0 for key in REGISTRY_STACK_IMAGE_KEYS}
    for compose in compose_files:
        if not compose.exists():
            continue
        text = compose.read_text()
        if "@latest" in text or ":latest" in text:
            failures.append(f"{compose.name}: latest tags are not allowed")
        for fallback in COMPOSE_FALLBACK_RE.finditer(text):
            key = fallback.group("key")
            fallback_counts[key] += 1
            expected = values.get(key)
            if expected and fallback.group("value") != expected:
                failures.append(
                    f"{compose.name}: {key} fallback must match versions.env"
                )

    for key, count in fallback_counts.items():
        if count == 0:
            failures.append(f"compose files: expected a {key} fallback")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
