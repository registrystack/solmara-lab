#!/usr/bin/env python3
"""Create ignored local operator keys and the Compose environment."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shlex
import subprocess
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives.asymmetric import ec, rsa

from compose_project_name import compose_project_name

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "config/evidence/local"
RANDOM_ENV_KEYS = (
    "CRA_RELAY_AUDIT_KEY",
    "NIA_RELAY_AUDIT_KEY",
    "MOSD_RELAY_AUDIT_KEY",
    "SIPF_RELAY_AUDIT_KEY",
    "SIPF_RELAY_CURSOR_KEY",
    "NAGDI_RELAY_AUDIT_KEY",
    "NAGDI_RELAY_CURSOR_KEY",
    "CHILD_BENEFIT_FEDERATOR_TOKEN",
    "PORTAL_SESSION_SECRET",
    "SOLMARA_ESIGNET_POSTGRES_PASSWORD",
    "REGISTRY_ESIGNET_KYC_KEYSTORE_PASSWORD",
    "REGISTRY_ESIGNET_KYC_TOKEN_SECRET",
    "REGISTRY_ESIGNET_PSUT_SECRET",
)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def raw_key() -> str:
    return secrets.token_urlsafe(32)


def p256_jwk() -> str:
    private = ec.generate_private_key(ec.SECP256R1()).private_numbers()
    public = private.public_numbers
    jwk = {
        "kty": "EC", "crv": "P-256", "alg": "ES256",
        "x": b64url(public.x.to_bytes(32, "big")),
        "y": b64url(public.y.to_bytes(32, "big")),
        "d": b64url(private.private_value.to_bytes(32, "big")),
    }
    thumbprint = {key: jwk[key] for key in ("crv", "kty", "x", "y")}
    jwk["kid"] = b64url(hashlib.sha256(json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()).digest())
    return json.dumps(jwk, separators=(",", ":"), sort_keys=True)


def rsa_jwk() -> str:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_numbers()
    public = private.public_numbers

    def encode(number: int) -> str:
        return b64url(number.to_bytes((number.bit_length() + 7) // 8, "big"))

    jwk = {
        "kty": "RSA", "alg": "RS256", "n": encode(public.n), "e": encode(public.e),
        "d": encode(private.d), "p": encode(private.p), "q": encode(private.q),
        "dp": encode(private.dmp1), "dq": encode(private.dmq1), "qi": encode(private.iqmp),
    }
    thumbprint = {key: jwk[key] for key in ("e", "kty", "n")}
    jwk["kid"] = b64url(hashlib.sha256(json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()).digest())
    return json.dumps(jwk, separators=(",", ":"), sort_keys=True)


def write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip("\n") + "\n", encoding="utf-8")
    path.chmod(0o600)


def create_once(path: Path, factory) -> None:
    if not path.exists():
        write_private(path, factory())


def load_environment(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("generated environment contains a malformed entry")
        key, encoded = line.split("=", 1)
        if key in values:
            raise ValueError("generated environment contains a duplicate entry")
        try:
            parsed = shlex.split(encoded, posix=True)
        except ValueError as exc:
            raise ValueError(
                "generated environment contains a malformed value"
            ) from exc
        if len(parsed) != 1 or not parsed[0]:
            raise ValueError(f"generated environment value is invalid for {key}")
        values[key] = parsed[0]
    return values


def create_environment_value(
    existing: dict[str, str], key: str, factory: Callable[[], str]
) -> str:
    value = existing.get(key)
    if value is not None:
        if not value:
            raise ValueError(f"generated environment value is invalid for {key}")
        return value
    return factory()


def compose_environment_values(
    existing: dict[str, str], operator_values: dict[str, str]
) -> dict[str, str]:
    values = {
        key: create_environment_value(existing, key, raw_key)
        for key in RANDOM_ENV_KEYS
    }
    values["PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64"] = create_environment_value(
        existing, "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64", rsa_private_key_b64
    )
    values.update(
        {
            "COMPOSE_PROJECT_NAME": compose_project_name(ROOT),
            "PORTAL_AUTH_PROVIDER": "mock",
            "PORTAL_ESIGNET_CLIENT_ID": "solmara-portal",
            "PORTAL_ESIGNET_CLIENT_KEY_ID": "solmara-portal-key-1",
            **operator_values,
        }
    )
    return values


def ensure_client_identifier(path: Path, client_id: str) -> None:
    """Write an exact public identifier while preserving unrelated material."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == client_id:
            path.chmod(0o600)
            return
        # Migrate the previous generator's single trailing newline only. Any
        # other value is operator-owned divergence and must fail closed.
        if current != f"{client_id}\n":
            raise ValueError(f"client identifier does not match {path.name}")
    path.write_text(client_id, encoding="utf-8")
    path.chmod(0o600)


def ensure_operator_material() -> dict[str, str]:
    cells = {
        "cra": ("cra-pension-evidence", "cra-citizen-evidence"),
        "nia": (), "sro": (),
        "mosd-programme": ("mosd-child-benefit-evidence",),
        "sipf": ("sipf-pension-evidence", "sipf-survivor-evidence"),
        "nagdi": ("nagdi-voucher-evidence", "nagdi-livestock-evidence"),
    }
    for cell, clients in cells.items():
        secret_root = LOCAL / "cells" / cell / "secrets"
        (LOCAL / "cells" / cell / "transit").mkdir(parents=True, exist_ok=True)
        create_once(secret_root / "signing.jwk", p256_jwk)
        create_once(secret_root / "audit-hmac-key", raw_key)
        create_once(secret_root / "subject-binding-hmac-key", raw_key)
        for client in clients:
            create_once(secret_root / f"{client}-client-key", p256_jwk)
            ensure_client_identifier(secret_root / f"{client}-client-id", client)

    mint = LOCAL / "cells" / "mint"
    for directory in (mint / "secrets", mint / "clients", mint / "transit"):
        directory.mkdir(parents=True, exist_ok=True)
    create_once(mint / "secrets/signing.jwk", p256_jwk)
    create_once(mint / "secrets/audit-hmac-key", raw_key)
    create_once(mint / "clients/nia-esignet-rsa-client-key", rsa_jwk)
    create_once(mint / "clients/solmara-demo-client-key", p256_jwk)
    return {
        "NIA_ESIGNET_CLIENT_PRIVATE_JWK": (mint / "clients/nia-esignet-rsa-client-key").read_text().strip(),
        "SOLMARA_EVIDENCE_CLIENT_KEY": str(mint / "clients/solmara-demo-client-key"),
    }


def ensure_tls() -> None:
    tls = LOCAL / "tls"
    tls.mkdir(parents=True, exist_ok=True)
    ca_key, ca_crt = tls / "ca.key", tls / "ca.crt"
    key, crt, csr = tls / "gateway.key", tls / "gateway.crt", tls / "gateway.csr"
    sans = [
        "localhost", "mint.solmara.registrystack.org", "evidence.solmara.invalid",
        "cra-relay.solmara.registrystack.org", "mosd-programme-relay.solmara.registrystack.org",
        "sipf-relay.solmara.registrystack.org", "nagdi-relay.solmara.registrystack.org",
    ]
    if all(path.exists() for path in (ca_key, ca_crt, key, crt)):
        certificate = subprocess.run(
            ["openssl", "x509", "-in", str(crt), "-noout", "-ext", "subjectAltName"],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout
        if all(f"DNS:{name}" in certificate for name in sans):
            return
    for path in (ca_key, ca_crt, key, crt, csr, tls / "ca.srl"):
        path.unlink(missing_ok=True)
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650", "-subj", "/CN=Solmara Lab CA", "-keyout", str(ca_key), "-out", str(ca_crt)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost", "-addext", "subjectAltName=" + ",".join(f"DNS:{name}" for name in sans), "-keyout", str(key), "-out", str(csr)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial", "-days", "3650", "-copy_extensions", "copy", "-out", str(crt)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csr.unlink()
    (tls / "ca.srl").unlink(missing_ok=True)
    ca_key.chmod(0o600)
    key.chmod(0o600)
    ca_crt.chmod(0o644)
    crt.chmod(0o644)


def rsa_private_key_b64() -> str:
    return base64.b64encode(subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"], check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout).decode()


def main() -> int:
    operator_values = ensure_operator_material()
    ensure_tls()
    output = ROOT / ".env"
    values = compose_environment_values(load_environment(output), operator_values)
    output.write_text("# Generated by scripts/gen-secrets.py. Do not commit.\n" + "\n".join(f"{key}={shlex.quote(value)}" for key, value in sorted(values.items())) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
