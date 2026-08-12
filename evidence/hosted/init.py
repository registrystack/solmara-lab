#!/usr/bin/env python3
"""Initialize hosted Evidence state without logging private material."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any


PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})
REPLACEMENTS = {
    "https://mint.evidence.solmara.invalid": "https://mint.solmara.registrystack.org",
    "https://cra-relay.evidence.solmara.invalid": "https://cra-relay.solmara.registrystack.org",
    "https://nia-relay.evidence.solmara.invalid": "https://nia-relay.solmara.registrystack.org",
    "https://sro-relay.evidence.solmara.invalid": "https://sro-relay.solmara.registrystack.org",
    "https://programme-relay.evidence.solmara.invalid": "https://mosd-programme-relay.solmara.registrystack.org",
    "https://sipf-relay.evidence.solmara.invalid": "https://sipf-relay.solmara.registrystack.org",
    "https://nagdi-relay.evidence.solmara.invalid": "https://nagdi-relay.solmara.registrystack.org",
    "secret:file/cra-relay-token": "secret:file/relay/cra/cra-relay-token",
    "secret:file/nia-relay-token": "secret:file/relay/nia/nia-relay-token",
    "secret:file/sro-relay-token": "secret:file/relay/sro/sro-relay-token",
    "secret:file/programme-relay-token": "secret:file/relay/programme/programme-relay-token",
    "secret:file/sipf-relay-token": "secret:file/relay/sipf/sipf-relay-token",
    "secret:file/nagdi-relay-token": "secret:file/relay/nagdi/nagdi-relay-token",
}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--bundle-source", type=Path, required=True)
    value.add_argument("--bundle-target", type=Path, required=True)
    value.add_argument("--evidence-secrets", type=Path, required=True)
    value.add_argument("--mint-secrets", type=Path, required=True)
    value.add_argument("--application-secrets", type=Path, required=True)
    value.add_argument("--mint-clients", type=Path, required=True)
    value.add_argument("--mint-public-keys", type=Path, required=True)
    value.add_argument("--evidence-audit", type=Path, required=True)
    value.add_argument("--mint-audit", type=Path, required=True)
    value.add_argument("--uid", type=int, default=65532)
    value.add_argument("--gid", type=int, default=65532)
    return value


def required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


def secret_value(name: str) -> str:
    value = required_environment(name)
    if len(value.encode("utf-8")) < 32 or "\x00" in value:
        raise ValueError(f"{name} must contain at least 32 bytes and no NUL")
    return value


def jwk(name: str, *, private: bool) -> dict[str, Any]:
    try:
        value = json.loads(required_environment(name))
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must contain one JSON JWK") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain one JSON JWK")
    if value.get("kty") != "EC" or value.get("crv") != "P-256":
        raise ValueError(f"{name} must be a P-256 EC JWK")
    if value.get("alg") != "ES256":
        raise ValueError(f"{name} must declare alg ES256")
    for member in ("kid", "x", "y"):
        if not isinstance(value.get(member), str) or not value[member]:
            raise ValueError(f"{name} must contain a non-empty {member}")
    private_members = PRIVATE_JWK_MEMBERS.intersection(value)
    if private:
        if private_members != {"d"} or not isinstance(value["d"], str) or not value["d"]:
            raise ValueError(f"{name} must contain only the P-256 private member d")
    elif private_members:
        raise ValueError(f"{name} must not contain private JWK members")
    return value


def prepare_directory(path: Path, mode: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"unsafe state directory: {path}")
    path.chmod(mode)


def require_clean_tree(path: Path) -> None:
    for entry in path.rglob("*"):
        if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
            raise ValueError(f"unsafe state entry: {entry}")


def clear_directory(path: Path) -> None:
    require_clean_tree(path)
    for entry in sorted(path.iterdir(), key=lambda item: item.name):
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def atomic_write(path: Path, value: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value.rstrip("\n") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_stable_secret(path: Path, value: str, mode: int = 0o600) -> None:
    normalized = value.rstrip("\n") + "\n"
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"unsafe stable secret path: {path}")
        existing = path.read_text(encoding="utf-8")
        if not hmac.compare_digest(existing, normalized):
            raise ValueError(f"refusing to replace stable secret: {path.name}")
        path.chmod(mode)
        return
    atomic_write(path, value, mode)


def hosted_evidence_config(source: str) -> str:
    value = source
    for old, new in REPLACEMENTS.items():
        if old not in value:
            raise ValueError(f"Evidence source config is missing expected value {old}")
        value = value.replace(old, new)
    lines = [
        line
        for line in value.splitlines()
        if line.strip() != "tlsTrustProfile: solmara-lab"
    ]
    value = "\n".join(lines) + "\n"
    value = value.replace("assuranceProfile: local", "assuranceProfile: production")
    value, replacements = re.subn(
        r"(?m)^(\s*activePublicJwkFile:)\s+\S+\s*$",
        r"\1 public-keys/active.jwk.json",
        value,
        count=1,
    )
    if replacements != 1:
        raise ValueError("Evidence source config must name one active public signing key")
    if (
        ".solmara.invalid" in value
        or "tlsTrustProfile: solmara-lab" in value
        or "assuranceProfile: production" not in value
    ):
        raise ValueError("hosted Evidence config retains a local-only endpoint")
    return value


def copy_bundle(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("bundle source must be a regular directory")
    require_clean_tree(source)
    prepare_directory(target, 0o755)
    clear_directory(target)
    for entry in source.iterdir():
        destination = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, destination)
        else:
            shutil.copy2(entry, destination)
    config = target / "evidence.yaml"
    atomic_write(config, hosted_evidence_config(config.read_text(encoding="utf-8")), 0o644)
    for entry in target.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def chown_tree(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)
    for entry in path.rglob("*"):
        os.chown(entry, uid, gid, follow_symlinks=False)


def initialize(args: argparse.Namespace) -> None:
    public_evidence = jwk("EVIDENCE_SIGNING_PUBLIC_JWK", private=False)
    public_mint = jwk("MINT_SIGNING_PUBLIC_JWK", private=False)
    private_client = jwk("SOLMARA_EVIDENCE_CLIENT_JWK", private=True)
    public_client = jwk("SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK", private=False)
    if any(private_client[key] != public_client[key] for key in ("kid", "x", "y")):
        raise ValueError("application public JWK does not match its private JWK")
    if public_evidence["kid"] == public_mint["kid"]:
        raise ValueError("Evidence and Mint must use distinct signing keys")

    private_directories = (
        args.evidence_secrets,
        args.mint_secrets,
        args.application_secrets,
        args.evidence_audit,
        args.mint_audit,
    )
    for directory in private_directories:
        prepare_directory(directory, 0o700)
        require_clean_tree(directory)
    prepare_directory(args.mint_clients, 0o755)
    require_clean_tree(args.mint_clients)
    prepare_directory(args.mint_public_keys, 0o755)
    require_clean_tree(args.mint_public_keys)

    write_stable_secret(
        args.evidence_secrets / "audit-hmac-key",
        secret_value("EVIDENCE_AUDIT_HMAC_KEY"),
    )
    write_stable_secret(
        args.evidence_secrets / "subject-binding-hmac-key",
        secret_value("EVIDENCE_SUBJECT_BINDING_HMAC_KEY"),
    )
    write_stable_secret(
        args.mint_secrets / "audit-hmac-key",
        secret_value("MINT_AUDIT_HMAC_KEY"),
    )
    atomic_write(args.application_secrets / "solmara-evidence-client.jwk", json.dumps(private_client, separators=(",", ":"), sort_keys=True), 0o600)

    client = {
        "clientId": "solmara-demo",
        "evidenceAudience": "https://id.registrystack.org/solmara/audience/demo-client",
        "keys": [public_client],
        "principal": "https://id.registrystack.org/solmara/principal/demo-client",
        "requesterTags": ["solmara-demo"],
    }
    atomic_write(args.mint_clients / "solmara-demo.yaml", json.dumps(client, indent=2, sort_keys=True), 0o644)
    copy_bundle(args.bundle_source, args.bundle_target)
    atomic_write(args.bundle_target / "public-keys" / "active.jwk.json", json.dumps(public_evidence, indent=2, sort_keys=True), 0o644)
    atomic_write(args.mint_public_keys / "active.jwk.json", json.dumps(public_mint, indent=2, sort_keys=True), 0o644)

    for directory in (*private_directories, args.mint_clients, args.mint_public_keys, args.bundle_target):
        chown_tree(directory, args.uid, args.gid)


def main() -> int:
    try:
        initialize(parser().parse_args())
    except (OSError, ValueError) as error:
        print(f"hosted-evidence-init: {error}", file=os.sys.stderr)
        return 1
    print("hosted-evidence-init: initialized private volumes and read-only configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
