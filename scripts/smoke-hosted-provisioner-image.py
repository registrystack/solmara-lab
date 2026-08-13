#!/usr/bin/env python3
"""Exercise hosted Evidence and Mint provisioning through the built image."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "config" / "evidence" / "local" / "cells"
GENERIC_ERROR = "hosted provisioner image smoke failed"
MINT_ORIGIN = "https://mint-authority-cells.solmara.registrystack.org"
CRA_RELAY_ORIGIN = "https://cra-relay-authority-cells.solmara.registrystack.org"


def _build_cells_module():
    path = ROOT / "evidence" / "scripts" / "build-cells.py"
    spec = importlib.util.spec_from_file_location("build_cells", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unavailable helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    path.chmod(0o400)


def _copy_secret(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    destination.chmod(0o400)


def _run(
    image: str, arguments: list[str], mounts: list[tuple[Path, str, bool]]
) -> None:
    secret_mounts = [
        mount for mount in mounts if mount[1] == "/tmp/solmara-provisioning"
    ]
    if len(secret_mounts) != 1 or not secret_mounts[0][2]:
        raise RuntimeError("invalid secret mount")
    secret_root = secret_mounts[0][0]
    secret_paths = sorted(secret_root.iterdir())
    if not secret_paths:
        raise RuntimeError("missing secrets")
    environment = os.environ.copy()
    secrets: dict[str, dict[str, str]] = {}
    service_secrets: list[dict[str, object]] = []
    for index, path in enumerate(secret_paths):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("invalid secret")
        secret_name = f"input-{index}"
        environment_name = f"SOLMARA_SMOKE_SECRET_{index}"
        environment[environment_name] = path.read_text(encoding="utf-8")
        secrets[secret_name] = {"environment": environment_name}
        service_secrets.append(
            {
                "source": secret_name,
                "target": f"/tmp/solmara-provisioning/{path.name}",
                "uid": "0",
                "gid": "0",
                "mode": 0o400,
            }
        )
    volumes = [
        {
            "type": "bind",
            "source": str(source),
            "target": target,
            "read_only": readonly,
        }
        for source, target, readonly in mounts
        if target != "/tmp/solmara-provisioning"
    ]
    compose = {
        "services": {
            "provision": {
                "image": image,
                "platform": "linux/amd64",
                "pull_policy": "never",
                "network_mode": "none",
                "read_only": False,
                "user": "0:0",
                "cap_drop": ["ALL"],
                "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER"],
                "security_opt": ["no-new-privileges:true"],
                "volumes": volumes,
                "secrets": service_secrets,
                "command": arguments,
            }
        },
        "secrets": secrets,
    }
    project = f"solmara-provisioner-smoke-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(
        prefix="solmara-provisioner-compose-"
    ) as temporary:
        compose_file = Path(temporary) / "compose.yaml"
        compose_file.write_text(
            yaml.safe_dump(compose, sort_keys=True), encoding="utf-8"
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--file",
            str(compose_file),
        ]
        try:
            subprocess.run(
                [
                    *command,
                    "up",
                    "--abort-on-container-exit",
                    "--exit-code-from",
                    "provision",
                ],
                check=True,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        finally:
            subprocess.run(
                [*command, "down", "--volumes", "--remove-orphans"],
                check=False,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def smoke(image: str, state_root: Path) -> None:
    helper = _build_cells_module()
    cra_input = state_root / "cra-input"
    cra_input.mkdir(parents=True)
    _write_json(
        cra_input / "signing-public.jwk",
        helper.public_jwk(LOCAL / "cra" / "secrets" / "signing.jwk"),
    )
    for name in ("audit-hmac-key", "subject-binding-hmac-key"):
        _copy_secret(LOCAL / "cra" / "secrets" / name, cra_input / name)
    for client in ("cra-pension-evidence", "cra-citizen-evidence"):
        _copy_secret(
            LOCAL / "cra" / "secrets" / f"{client}-client-key",
            cra_input / f"{client}-client-key",
        )
    cra = state_root / "cra"
    for name in ("runtime", "secrets", "extracts"):
        (cra / name).mkdir(parents=True)
    cra_mounts = [
        (cra_input, "/tmp/solmara-provisioning", True),
        (cra / "runtime", "/provisioned/runtime", False),
        (cra / "secrets", "/provisioned/secrets", False),
        (cra / "extracts", "/provisioned/extracts", False),
    ]
    cra_arguments = [
        "provision",
        "--target",
        "cra-evidence",
        "--assets",
        "/opt/solmara-hosted-assets",
        "--secrets",
        "/tmp/solmara-provisioning",
        "--runtime-output",
        "/provisioned/runtime",
        "--secret-output",
        "/provisioned/secrets",
        "--extract-output",
        "/provisioned/extracts",
        "--bind-host",
        "172.29.1.21",
        "--mint-origin",
        MINT_ORIGIN,
        "--relay-origin",
        CRA_RELAY_ORIGIN,
    ]
    _run(image, cra_arguments, cra_mounts)
    _run(image, cra_arguments, cra_mounts)

    mint_input = state_root / "mint-input"
    mint_input.mkdir()
    _write_json(
        mint_input / "signing-public.jwk",
        helper.public_jwk(LOCAL / "mint" / "secrets" / "signing.jwk"),
    )
    _copy_secret(
        LOCAL / "mint" / "secrets" / "audit-hmac-key",
        mint_input / "audit-hmac-key",
    )
    clients = {
        "cra": ("cra-pension-evidence", "cra-citizen-evidence"),
        "mosd-programme": ("mosd-child-benefit-evidence",),
        "sipf": ("sipf-pension-evidence", "sipf-survivor-evidence"),
        "nagdi": ("nagdi-voucher-evidence", "nagdi-livestock-evidence"),
    }
    for cell, names in clients.items():
        for client in names:
            _write_json(
                mint_input / f"{client}-public.jwk",
                helper.public_jwk(LOCAL / cell / "secrets" / f"{client}-client-key"),
            )
    _write_json(
        mint_input / "nia-esignet-public.jwk",
        helper.public_jwk(LOCAL / "mint" / "clients" / "nia-esignet-rsa-client-key"),
    )
    _write_json(
        mint_input / "solmara-demo-client-public.jwk",
        helper.public_jwk(LOCAL / "mint" / "clients" / "solmara-demo-client-key"),
    )
    mint = state_root / "mint"
    for name in ("runtime", "secrets"):
        (mint / name).mkdir(parents=True)
    mint_mounts = [
        (mint_input, "/tmp/solmara-provisioning", True),
        (mint / "runtime", "/provisioned/runtime", False),
        (mint / "secrets", "/provisioned/secrets", False),
    ]
    mint_arguments = [
        "provision",
        "--target",
        "mint",
        "--assets",
        "/opt/solmara-hosted-assets",
        "--secrets",
        "/tmp/solmara-provisioning",
        "--runtime-output",
        "/provisioned/runtime",
        "--secret-output",
        "/provisioned/secrets",
        "--bind-host",
        "172.29.1.20",
        "--mint-origin",
        MINT_ORIGIN,
    ]
    _run(image, mint_arguments, mint_mounts)
    _run(image, mint_arguments, mint_mounts)

    cra_config = yaml.safe_load((cra / "runtime/bundle/evidence.yaml").read_text())
    if not (
        cra / "runtime/bundle" / cra_config["signing"]["activePublicJwkFile"]
    ).is_file():
        raise RuntimeError("missing Evidence public key")
    if len(list((cra / "extracts").glob("*.sqlite"))) != 1:
        raise RuntimeError("invalid Evidence extract publication")
    mint_config = yaml.safe_load((mint / "runtime/mint.yaml").read_text())
    if not (mint / "runtime" / mint_config["signing"]["activePublicJwkFile"]).is_file():
        raise RuntimeError("missing Mint public key")
    if len(list((mint / "runtime/clients").glob("*.yaml"))) != 9:
        raise RuntimeError("invalid Mint client publication")


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--image", required=True)
    parser.add_argument("--state-root", type=Path)
    try:
        arguments = parser.parse_args()
        state_root = arguments.state_root or Path(
            tempfile.mkdtemp(prefix="solmara-hosted-provisioner-smoke-")
        )
        state_root.mkdir(parents=True, exist_ok=True)
        smoke(arguments.image, state_root.resolve())
    except Exception:  # noqa: BLE001 - CI output is a public redaction boundary.
        print(GENERIC_ERROR, file=sys.stderr)
        return 1
    print("hosted provisioner image smoke passed")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main())
