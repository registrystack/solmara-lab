#!/usr/bin/env python3
"""Validate the coherent immutable Registry Stack release pins."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r"^[0-9a-f]{64}$")
HTTPS = re.compile(r"^https://[^\s]+$")
REQUIRED_VERSION = "0.20.1"


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
        "REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256",
        "REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256",
        "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256",
    ):
        value = values.get(key, "")
        if value and not DIGEST.fullmatch(value):
            failures.append(f"{key} must be 64 lowercase hex characters")
        if require_public and not value:
            failures.append(f"{key} is not published; v{REQUIRED_VERSION} promotion is blocked")
    asset_names = {
        "REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL": f"evidence-v{REQUIRED_VERSION}-linux-amd64",
        "REGISTRY_STACK_RELEASE_MINT_ASSET_URL": f"mint-v{REQUIRED_VERSION}-linux-amd64",
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
    if values.get("ESIGNET_AUTHENTICATOR_VERSION") != "0.2.0":
        failures.append("ESIGNET_AUTHENTICATOR_VERSION must be 0.2.0")
    release_url = "https://github.com/jeremi/esignet-relay-authenticator/releases/tag/v0.2.0"
    if values.get("ESIGNET_AUTHENTICATOR_RELEASE_URL") != release_url:
        failures.append("ESIGNET_AUTHENTICATOR_RELEASE_URL must bind the exact v0.2.0 release")
    jar_url = values.get("ESIGNET_AUTHENTICATOR_JAR_URL", "")
    jar_sha = values.get("ESIGNET_AUTHENTICATOR_JAR_SHA256", "")
    if jar_url and not HTTPS.fullmatch(jar_url):
        failures.append("ESIGNET_AUTHENTICATOR_JAR_URL must be an exact HTTPS URL")
    if jar_sha and not DIGEST.fullmatch(jar_sha):
        failures.append("ESIGNET_AUTHENTICATOR_JAR_SHA256 must be 64 lowercase hex characters")
    expected_base = "https://github.com/jeremi/esignet-relay-authenticator/releases/download/v0.2.0/"
    if jar_url and jar_url != expected_base + "esignet-relay-authenticator-0.2.0.jar":
        failures.append("ESIGNET_AUTHENTICATOR_JAR_URL must bind the exact v0.2.0 release asset")
    if values.get("ESIGNET_AUTHENTICATOR_CHECKSUM_URL", "") != expected_base + "esignet-relay-authenticator-0.2.0.jar.sha256":
        failures.append("ESIGNET_AUTHENTICATOR_CHECKSUM_URL must bind the exact v0.2.0 checksum asset")
    if require_public and (not jar_url or not jar_sha):
        failures.append("eSignet authenticator v0.2.0 JAR URL/checksum is not published; promotion is blocked")
    return failures


def main() -> int:
    failures = validate(read_versions(ROOT / "versions.env"), require_public="--require-public" in sys.argv[1:])
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
