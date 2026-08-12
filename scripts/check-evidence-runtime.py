#!/usr/bin/env python3
"""Validate the authored Evidence bundle and paired Mint configuration."""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "config/evidence/local"


def main() -> int:
    version = versions()["REGISTRYCTL_VERSION"]
    evidence = pinned_tool("evidence", version)
    evidencectl = pinned_tool("evidencectl", version)
    mint = pinned_tool("mint", version)
    required = (
        LOCAL / "evidence/audit-hmac-key",
        LOCAL / "evidence/signing-p256-private-jwk",
        LOCAL / "evidence/signing-p256-public.jwk",
        LOCAL / "evidence/subject-binding-hmac-key",
        LOCAL / "mint/audit-hmac-key",
        LOCAL / "mint/signing.jwk",
        LOCAL / "mint/signing-public.jwk",
        LOCAL / "mint/clients/solmara-demo.yaml",
        LOCAL / "tls/ca.crt",
        LOCAL / "tls/gateway.crt",
    )
    missing = [path for path in required if not path.is_file()]
    if missing:
        names = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise SystemExit(
            f"missing generated Evidence material: {names}; run `just gen-secrets`"
        )

    with tempfile.TemporaryDirectory(prefix="solmara-evidence-check-") as directory:
        stage = Path(directory)
        evidence_project = stage / "evidence"
        shutil.copytree(ROOT / "evidence", evidence_project)
        evidence_public = LOCAL / "evidence/signing-p256-public.jwk"
        evidence_public_name = public_key_filename(evidence_public)
        staged_evidence_public = (
            evidence_project / "bundle/public-keys" / evidence_public_name
        )
        staged_evidence_public.parent.mkdir(exist_ok=True)
        shutil.copy2(
            evidence_public,
            staged_evidence_public,
        )
        evidence_config = evidence_project / "bundle/evidence.yaml"
        evidence_config.write_text(
            evidence_config.read_text().replace(
                "public-keys/active.jwk.json",
                f"public-keys/{evidence_public_name}",
            )
        )
        make_immutable(evidence_project / "bundle")
        audit = stage / "audit"
        audit.mkdir(mode=0o700)
        evidence_secrets = stage / "evidence-secrets"
        evidence_secrets.mkdir(mode=0o700)
        for name in (
            "audit-hmac-key",
            "signing-p256-private-jwk",
            "subject-binding-hmac-key",
        ):
            shutil.copy2(LOCAL / "evidence" / name, evidence_secrets / name)
        for authority in ("cra", "nia", "sro", "programme", "sipf", "nagdi"):
            token = evidence_secrets / f"{authority}-relay-token"
            token.write_text("fixture-only-token")
            token.chmod(0o600)
        staged_ca = stage / "ca.crt"
        shutil.copy2(LOCAL / "tls/ca.crt", staged_ca)
        staged_ca.chmod(staged_ca.stat().st_mode & ~stat.S_IWUSR)

        runtime = (evidence_project / "runtime.yaml").read_text()
        replacements = {
            "/etc/registry-evidence/bundle": str(evidence_project / "bundle"),
            "bindHost: 172.29.0.10": "bindHost: 127.0.0.1",
            "/run/secrets/registry-evidence": str(evidence_secrets),
            "/var/lib/registry-evidence/audit/evidence.jsonl": str(
                audit / "evidence.jsonl"
            ),
            "/etc/registry-evidence/tls/lab-ca.crt": str(staged_ca),
        }
        for old, new in replacements.items():
            runtime = runtime.replace(old, new)
        staged_runtime = evidence_project / "runtime.yaml"
        staged_runtime.write_text(runtime)
        staged_runtime.chmod(staged_runtime.stat().st_mode & ~stat.S_IWUSR)

        mint_public = LOCAL / "mint/signing-public.jwk"
        mint_public_name = public_key_filename(mint_public)
        mint_config = (
            (ROOT / "evidence/mint.yaml")
            .read_text()
            .replace("public-keys/active.jwk.json", f"public-keys/{mint_public_name}")
        )
        mint_replacements = {
            "/run/secrets/registry-mint": str(LOCAL / "mint"),
            "/var/lib/registry-mint/audit/mint.jsonl": str(audit / "mint.jsonl"),
            "/etc/registry-mint/clients": str(LOCAL / "mint/clients"),
        }
        for old, new in mint_replacements.items():
            mint_config = mint_config.replace(old, new)
        staged_mint = stage / "mint.yaml"
        staged_mint.write_text(mint_config)
        staged_mint_public = stage / "public-keys" / mint_public_name
        staged_mint_public.parent.mkdir(exist_ok=True)
        shutil.copy2(mint_public, staged_mint_public)
        staged_mint_public.chmod(staged_mint_public.stat().st_mode & ~stat.S_IWUSR)

        subprocess.run([mint, "check", "--config", str(staged_mint)], check=True)
        subprocess.run(
            [
                evidencectl,
                "fixtures",
                "run",
                "--project",
                str(evidence_project),
                "--evidence-bin",
                str(evidence),
            ],
            check=True,
        )
    return 0


def versions() -> dict[str, str]:
    return {
        key: value
        for line in (ROOT / "versions.env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
        for key, value in [line.split("=", 1)]
    }


def public_key_filename(path: Path) -> str:
    public = json.loads(path.read_text())
    kid = public.get("kid")
    if not isinstance(kid, str) or len(kid) != 43:
        raise SystemExit(f"{path.relative_to(ROOT)} does not contain a thumbprint kid")
    return f"{kid}.jwk.json"


def pinned_tool(command: str, expected: str) -> Path:
    completed = subprocess.run(
        [ROOT / "scripts/registry-stack-tool.py", "path", command],
        check=True,
        capture_output=True,
        text=True,
    )
    path = Path(completed.stdout.strip())
    output = subprocess.run(
        [path, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if output != f"{command} {expected}":
        raise SystemExit(f"{path.name} did not report {command} {expected}")
    return path


def make_immutable(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
