#!/usr/bin/env python3
"""Validate the coherent immutable Registry Stack release pins."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r"^[0-9a-f]{64}$")
HTTPS = re.compile(r"^https://[^\s]+$")
REQUIRED_VERSION = "0.23.0"


def read_versions(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            result[key] = value
    return result


def validate(values: dict[str, str], *, require_public: bool) -> list[str]:
    failures: list[str] = []
    if values.get("REGISTRY_STACK_REQUIRED_VERSION") != REQUIRED_VERSION:
        failures.append(f"REGISTRY_STACK_REQUIRED_VERSION must be {REQUIRED_VERSION}")
    source_ref = values.get("REGISTRY_STACK_SOURCE_REF", "")
    expected_source_ref = f"v{REQUIRED_VERSION}"
    if source_ref and source_ref != expected_source_ref:
        failures.append(f"REGISTRY_STACK_SOURCE_REF must be {expected_source_ref}")
    if require_public and not source_ref:
        failures.append(f"REGISTRY_STACK_SOURCE_REF must bind the published {expected_source_ref} tag")
    source_commit = values.get("REGISTRY_STACK_SOURCE_COMMIT", "")
    if source_commit and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        failures.append("REGISTRY_STACK_SOURCE_COMMIT must be 40 lowercase hex characters")
    if require_public and not source_commit:
        failures.append(f"REGISTRY_STACK_SOURCE_COMMIT is not final; v{REQUIRED_VERSION} promotion is blocked")
    for key in (
        "REGISTRY_STACK_RELEASE_RELAY_DIGEST",
        "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256",
    ):
        value = values.get(key, "")
        if value and not DIGEST.fullmatch(value):
            failures.append(f"{key} must be 64 lowercase hex characters")
        if require_public and not value:
            failures.append(f"{key} is not published; v{REQUIRED_VERSION} promotion is blocked")
    asset_names = {
        "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL": f"relayctl-v{REQUIRED_VERSION}-linux-amd64",
    }
    release_base = f"https://github.com/registrystack/registry-stack/releases/download/v{REQUIRED_VERSION}/"
    for key, asset_name in asset_names.items():
        asset_url = values.get(key, "")
        if asset_url and not HTTPS.fullmatch(asset_url):
            failures.append(f"{key} must be an exact HTTPS URL")
        elif asset_url and asset_url != release_base + asset_name:
            failures.append(f"{key} must bind the exact v{REQUIRED_VERSION} linux-amd64 asset")
        if require_public and not asset_url:
            failures.append(f"{key} is not published; v{REQUIRED_VERSION} promotion is blocked")
    expected = {
        "ESIGNET_SOURCE_VERSION": "2.0.0-beta.1",
        "ESIGNET_SOURCE_COMMIT": "df0d0e771dae16eb2597b8e5b5dc65e70baa7f86",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            failures.append(f"{key} must be {value}")
    archive_digest = values.get("ESIGNET_SOURCE_ARCHIVE_SHA256", "")
    if not DIGEST.fullmatch(archive_digest):
        failures.append("ESIGNET_SOURCE_ARCHIVE_SHA256 must be 64 lowercase hex characters")
    # Native provider candidates are local build inputs, not published release assets.
    # Hosted image publication verifies the final image digests in its manifest gate.
    return failures


def main() -> int:
    failures = validate(read_versions(ROOT / "versions.env"), require_public="--require-public" in sys.argv[1:])
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
