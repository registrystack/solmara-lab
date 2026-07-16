#!/usr/bin/env python3
"""Verify Registry Stack image pins match a published release tag."""

from __future__ import annotations

import re
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_KEYS = {
    "REGISTRY_RELAY_IMAGE": "ghcr.io/registrystack/registry-relay",
    "REGISTRY_NOTARY_IMAGE": "ghcr.io/registrystack/registry-notary",
}
PIN_RE = re.compile(r"^(?P<image>[^@\s]+)@(?P<digest>sha256:[0-9a-f]{64})$")
DIGEST_RE = re.compile(r"^Digest:\s+(sha256:[0-9a-f]{64})$", re.MULTILINE)


def main(argv: list[str]) -> int:
    tag = argv[1] if len(argv) > 1 else "v0.10.0"
    versions = read_versions(ROOT / "versions.env")
    failures: list[str] = []

    for key, image in IMAGE_KEYS.items():
        pinned = os.environ.get(key) or versions.get(key)
        source = "environment" if os.environ.get(key) else "versions.env"
        if not pinned:
            failures.append(f"{key} is missing from {source}")
            continue
        match = PIN_RE.match(pinned)
        if not match:
            failures.append(f"{key} must be image@sha256:<digest>")
            continue
        if match.group("image") != image:
            failures.append(f"{key} points at {match.group('image')}, expected {image}")
            continue
        release_digest = inspect_tag_digest(f"{image}:{tag}")
        if release_digest != match.group("digest"):
            failures.append(
                f"{key} from {source} pins {match.group('digest')}, "
                f"but {image}:{tag} resolves to {release_digest}"
            )

    if failures:
        for failure in failures:
            print(f"check-release-pins: {failure}", file=sys.stderr)
        return 1

    print(f"check-release-pins: Registry Stack images match {tag}")
    return 0


def read_versions(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def inspect_tag_digest(ref: str) -> str:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    match = DIGEST_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"could not find digest in `docker buildx imagetools inspect {ref}` output")
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
