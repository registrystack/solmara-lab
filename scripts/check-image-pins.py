#!/usr/bin/env python3
"""Validate image pin conventions for the lab."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINE_RE = re.compile(r"^([A-Z0-9_]+)=([^#\s]*)$")
PIN_RE = re.compile(r"^[^#\s]+@sha256:[0-9a-f]{64}$")
OFFICIAL_RUNTIME_REPOSITORIES = {
    "REGISTRY_RELAY_IMAGE": "relay",
    "SOLMARA_EVIDENCE_IMAGE": "evidence",
    "SOLMARA_MINT_IMAGE": "mint",
}
SOURCE_IMAGE_KEYS = set(OFFICIAL_RUNTIME_REPOSITORIES)
PINNED_IMAGE_KEYS = {
    "VOLUME_INIT_IMAGE", "LOCAL_EDGE_IMAGE", "PYTHON_STATIC_IMAGE",
    "NODE_BUILD_IMAGE", "UV_BUILD_IMAGE",
    "ESIGNET_REDIS_IMAGE", "ESIGNET_BASE_IMAGE", "ESIGNET_UI_IMAGE",
    "ESIGNET_POSTGRES_IMAGE",
}


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
        if key in OFFICIAL_RUNTIME_REPOSITORIES:
            repository = OFFICIAL_RUNTIME_REPOSITORIES[key]
            expected = f"ghcr.io/registrystack/{repository}@sha256:"
            if not value.startswith(expected) or not PIN_RE.match(value):
                failures.append(
                    f"versions.env:{line_no}: {key} must use "
                    f"{expected}<64 lowercase hex>"
                )
        if key in PINNED_IMAGE_KEYS and not PIN_RE.match(value):
            failures.append(f"versions.env:{line_no}: {key} must use image@sha256:<64 hex>")
        if "@latest" in value or ":latest" in value:
            failures.append(f"versions.env:{line_no}: latest tags are not allowed")

    for key in PINNED_IMAGE_KEYS | SOURCE_IMAGE_KEYS:
        if key not in values:
            failures.append(f"versions.env: {key} is required")

    compose_files = [ROOT / "compose.yaml", ROOT / "compose.esignet.yaml"]
    required_counts = {key: 0 for key in SOURCE_IMAGE_KEYS}
    for compose in compose_files:
        if not compose.exists():
            continue
        text = compose.read_text()
        if "@latest" in text or ":latest" in text:
            failures.append(f"{compose.name}: latest tags are not allowed")
        for key in SOURCE_IMAGE_KEYS:
            required_counts[key] += text.count(f"${{{key}:?")

    for key, count in required_counts.items():
        if count == 0:
            failures.append(f"compose files: expected a required {key} reference")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
