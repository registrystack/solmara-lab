#!/usr/bin/env python3
"""Build deployable Evidence/Mint config from authored templates and operator keys."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric import ec, rsa


ROOT = Path(__file__).resolve().parents[2]
CELL_ROOT = ROOT / "evidence" / "cells"
CELLS = ("cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
RELAY_CLIENTS = {
    "cra-pension-evidence": ("solmara:relay:cra:death-by-uin", "https://id.registrystack.org/solmara/purpose/pension-payment-review"),
    "cra-citizen-evidence": ("solmara:relay:cra:citizen-link-by-uin", "https://id.registrystack.org/solmara/purpose/citizen-self-service"),
    "mosd-child-benefit-evidence": ("solmara:relay:mosd:by-uin", "https://id.registrystack.org/solmara/purpose/child-benefit-review"),
    "sipf-pension-evidence": ("solmara:relay:sipf:by-pensioner-uin", "https://id.registrystack.org/solmara/purpose/pension-payment-review"),
    "sipf-survivor-evidence": ("solmara:relay:sipf:by-spouse-uin", "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination"),
    "nagdi-voucher-evidence": ("solmara:relay:nagdi:voucher-by-farmer-id", "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"),
    "nagdi-livestock-evidence": ("solmara:relay:nagdi:movement-by-farmer-id", "https://id.registrystack.org/solmara/purpose/livestock-movement-control"),
    "nia-esignet": ("solmara:relay:nia:esignet-userinfo", "https://id.registrystack.org/solmara/purpose/esignet-identity-verification"),
}
CLIENT_CELLS = {
    "cra-pension-evidence": "cra",
    "cra-citizen-evidence": "cra",
    "mosd-child-benefit-evidence": "mosd-programme",
    "sipf-pension-evidence": "sipf",
    "sipf-survivor-evidence": "sipf",
    "nagdi-voucher-evidence": "nagdi",
    "nagdi-livestock-evidence": "nagdi",
}


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def public_jwk(private_path: Path) -> dict[str, str]:
    value = json.loads(private_path.read_text(encoding="utf-8"))
    if value.get("kty") == "RSA":
        required = {"kty", "alg", "n", "e", "d", "p", "q", "dp", "dq", "qi", "kid"}
        if set(value) != required or value.get("alg") != "RS256":
            raise ValueError(f"{private_path}: expected an exact private RS256 JWK")

        def decode(member: str) -> int:
            encoded = value[member]
            return int.from_bytes(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)), "big")

        private = rsa.RSAPrivateNumbers(
            p=decode("p"), q=decode("q"), d=decode("d"), dmp1=decode("dp"),
            dmq1=decode("dq"), iqmp=decode("qi"),
            public_numbers=rsa.RSAPublicNumbers(e=decode("e"), n=decode("n")),
        )
        try:
            derived = private.private_key().public_key().public_numbers()
        except ValueError as exc:
            raise ValueError(f"{private_path}: private RS256 JWK members are inconsistent") from exc
        result = {"e": b64url(derived.e.to_bytes((derived.e.bit_length() + 7) // 8, "big")), "kty": "RSA", "n": b64url(derived.n.to_bytes((derived.n.bit_length() + 7) // 8, "big"))}
        thumbprint = hashlib.sha256(json.dumps(result, separators=(",", ":"), sort_keys=True).encode()).digest()
        result["alg"] = "RS256"
        result["kid"] = b64url(thumbprint)
        if any(value[key] != result[key] for key in ("n", "e", "kid")):
            raise ValueError(f"{private_path}: private JWK public members or kid do not match its key")
        return result
    if set(value) != {"kty", "crv", "alg", "x", "y", "d", "kid"} or value.get("kty") != "EC" or value.get("crv") != "P-256" or value.get("alg") != "ES256":
        raise ValueError(f"{private_path}: expected an exact private ES256 P-256 JWK")
    private_value = int.from_bytes(base64.urlsafe_b64decode(value["d"] + "=="), "big")
    public = ec.derive_private_key(private_value, ec.SECP256R1()).public_key().public_numbers()
    result = {"crv": "P-256", "kty": "EC", "x": b64url(public.x.to_bytes(32, "big")), "y": b64url(public.y.to_bytes(32, "big"))}
    thumbprint = hashlib.sha256(json.dumps(result, separators=(",", ":"), sort_keys=True).encode()).digest()
    result["alg"] = "ES256"
    result["kid"] = b64url(thumbprint)
    if value["x"] != result["x"] or value["y"] != result["y"] or value["kid"] != result["kid"]:
        raise ValueError(f"{private_path}: private JWK public members or kid do not match its scalar")
    return result


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def build(private_root: Path, output: Path, evidence_binary: Path | None) -> None:
    if output.exists():
        raise ValueError(f"refusing to overwrite generated output: {output}")
    for cell in CELLS:
        destination = output / "cells" / cell
        shutil.copytree(CELL_ROOT / cell, destination)
        cell_public = public_jwk(private_root / cell / "secrets" / "signing.jwk")
        config_path = destination / "bundle" / "evidence.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["signing"]["activePublicJwkFile"] = f"public-keys/{cell_public['kid']}.jwk.json"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        write_json(destination / "bundle" / "public-keys" / f"{cell_public['kid']}.jwk.json", cell_public)
        make_read_only(destination / "bundle")
        if evidence_binary:
            subprocess.run([str(evidence_binary), "bundle-check", "--bundle", str(destination / "bundle")], check=True)
        make_read_only(destination)

    mint_destination = output / "mint"
    mint_destination.mkdir(parents=True)
    shutil.copy2(ROOT / "evidence" / "mint.yaml", mint_destination / "mint.yaml")
    mint_public = public_jwk(private_root / "mint" / "secrets" / "signing.jwk")
    mint_config_path = mint_destination / "mint.yaml"
    mint_config = yaml.safe_load(mint_config_path.read_text(encoding="utf-8"))
    mint_config["signing"]["activePublicJwkFile"] = f"public-keys/{mint_public['kid']}.jwk.json"
    mint_config_path.write_text(yaml.safe_dump(mint_config, sort_keys=False), encoding="utf-8")
    write_json(mint_destination / "public-keys" / f"{mint_public['kid']}.jwk.json", mint_public)
    for client, (scope, purpose) in RELAY_CLIENTS.items():
        registration = {
            "clientId": client,
            "principal": f"https://id.registrystack.org/solmara/client/{client}",
            "authorization": {"scopes": [scope], "claims": {"purpose": purpose}},
            "keys": [public_jwk(
                private_root / CLIENT_CELLS[client] / "secrets" / f"{client}-client-key"
                if client in CLIENT_CELLS
                else private_root / "mint" / "clients" / "nia-esignet-rsa-client-key"
            )],
        }
        path = mint_destination / "clients" / f"{client}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(registration, sort_keys=False), encoding="utf-8")
    application = {
        "clientId": "solmara-demo",
        "principal": "https://id.registrystack.org/solmara/client/solmara-demo",
        "evidenceAudience": "https://id.registrystack.org/solmara/audience/demo-client",
        "requesterTags": ["solmara-demo"],
        "keys": [public_jwk(private_root / "mint" / "clients" / "solmara-demo-client-key")],
    }
    application_path = mint_destination / "clients" / "solmara-demo.yaml"
    application_path.write_text(yaml.safe_dump(application, sort_keys=False), encoding="utf-8")
    make_read_only(mint_destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence-binary", type=Path)
    args = parser.parse_args()
    build(args.private_key_root.resolve(), args.output.resolve(), args.evidence_binary)


if __name__ == "__main__":
    main()
