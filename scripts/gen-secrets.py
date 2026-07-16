#!/usr/bin/env python3
"""Generate local .env credentials for Solmara Lab."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import shlex
import subprocess
from pathlib import Path

from compose_project_name import compose_project_name

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_SSL_DIR = ROOT / "config" / "postgres" / "ssl"

RAW_HASH_PAIRS = [
    ("CRA_CHILD_BENEFIT_CLIENT_TOKEN", "CRA_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("CRA_PENSION_CLIENT_TOKEN", "CRA_PENSION_CLIENT_TOKEN_HASH"),
    ("CRA_CITIZEN_CLIENT_TOKEN", "CRA_CITIZEN_CLIENT_TOKEN_HASH"),
    ("NIA_CHILD_BENEFIT_CLIENT_TOKEN", "NIA_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("NIA_CITIZEN_CLIENT_TOKEN", "NIA_CITIZEN_CLIENT_TOKEN_HASH"),
    ("SRO_CHILD_BENEFIT_CLIENT_TOKEN", "SRO_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    (
        "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
        "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
    ),
    ("SIPF_PENSION_CLIENT_TOKEN", "SIPF_PENSION_CLIENT_TOKEN_HASH"),
    ("NAGDI_NOTARY_TOKEN", "NAGDI_CLIENT_TOKEN_HASH"),
]

JWK_KIDS = {
    "CRA_RELAY_WORKLOAD_JWK": "solmara-cra-relay-workload-key-1",
    "NIA_RELAY_WORKLOAD_JWK": "solmara-nia-relay-workload-key-1",
    "NIA_ESIGNET_RELAY_WORKLOAD_JWK": "solmara-nia-esignet-relay-workload-key-1",
    "SRO_RELAY_WORKLOAD_JWK": "solmara-sro-relay-workload-key-1",
    "PROGRAMME_RELAY_WORKLOAD_JWK": "solmara-programme-relay-workload-key-1",
    "SIPF_RELAY_WORKLOAD_JWK": "solmara-sipf-relay-workload-key-1",
    "NAGDI_RELAY_WORKLOAD_JWK": "solmara-nagdi-relay-workload-key-1",
    "NIA_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:authority:nia#issuer-key-1",
    "SIPF_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:authority:sipf#issuer-key-1",
    "NAGDI_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:authority:nagdi#issuer-key-1",
}

DIRECT_PROJECT_SECRET_NAMES = {
    "SOLMARA_NIA_DATABASE_URL",
    "SOLMARA_SIPF_DATABASE_URL",
}


def raw_key() -> str:
    return secrets.token_urlsafe(32)


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def local_ed25519_jwk(kid: str) -> str:
    private_der = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-outform", "DER"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    public_der = subprocess.run(
        ["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"],
        input=private_der,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    private_seed = private_der[-32:]
    public_key = public_der[-32:]
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "alg": "EdDSA",
        "x": b64url(public_key),
        "d": b64url(private_seed),
    }
    return json.dumps(jwk, separators=(",", ":"), sort_keys=True)


def local_rsa_private_key_b64() -> str:
    private_pem = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    return base64.b64encode(private_pem).decode("ascii")


def ensure_postgres_tls() -> None:
    POSTGRES_SSL_DIR.mkdir(parents=True, exist_ok=True)
    key_path = POSTGRES_SSL_DIR / "server.key"
    cert_path = POSTGRES_SSL_DIR / "server.crt"
    for path in (key_path, cert_path):
        path.unlink(missing_ok=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "365",
            "-subj",
            "/CN=postgres",
            "-addext",
            "subjectAltName=DNS:postgres,IP:127.0.0.1",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    key_path.chmod(0o600)
    cert_path.chmod(0o644)


def env_line(key: str, value: str) -> str:
    return f"{key}={shlex.quote(value)}"


def write_env_file(output: Path, values: dict[str, str], header: str) -> None:
    lines = [header, *[env_line(key, values[key]) for key in sorted(values)]]
    output.write_text("\n".join(lines) + "\n")
    output.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    ensure_postgres_tls()
    postgres_user = "solmara_registry"
    postgres_password = raw_key()
    postgres_db = "solmara_lab"
    nia_source_password = raw_key()
    sipf_source_password = raw_key()
    values: dict[str, str] = {
        "COMPOSE_PROJECT_NAME": compose_project_name(ROOT),
        "CRA_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "CRA_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "CRA_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "CRA_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "CRA_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "CRA_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "CRA_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "CRA_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "NIA_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "NIA_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "NIA_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "NIA_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "NIA_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "NIA_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "NIA_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "NIA_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "SRO_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "SRO_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "SRO_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "SRO_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "SRO_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "SRO_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "SRO_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "SRO_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "PROGRAMME_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "PROGRAMME_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "PROGRAMME_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "PROGRAMME_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "PROGRAMME_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "PROGRAMME_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "PROGRAMME_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "PROGRAMME_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "SIPF_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "SIPF_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "SIPF_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "SIPF_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "SIPF_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "SIPF_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "SIPF_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "SIPF_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "NAGDI_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "NAGDI_RELAY_AUDIT_PSEUDONYM_EPOCH_1": raw_key(),
        "NAGDI_RELAY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "NAGDI_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD": raw_key(),
        "NAGDI_RELAY_POSTGRES_KEYRING_READER_PASSWORD": raw_key(),
        "NAGDI_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "NAGDI_NOTARY_POSTGRES_MIGRATOR_PASSWORD": raw_key(),
        "NAGDI_NOTARY_POSTGRES_RUNTIME_PASSWORD": raw_key(),
        "SOLMARA_RELAY_KEY_ACTIVE_WRITE_DEADLINE_UNIX_MS": "4102444800000",
        "SOLMARA_RELAY_AUDIT_EVENT_RETENTION_MS": "2592000000",
        "REGISTRY_ESIGNET_KYC_KEYSTORE_PASSWORD": raw_key(),
        "REGISTRY_ESIGNET_KYC_TOKEN_SECRET": raw_key(),
        "REGISTRY_ESIGNET_PSUT_SECRET": raw_key(),
        "PORTAL_SESSION_SECRET": raw_key(),
        "PORTAL_AUTH_PROVIDER": "mock",
        "PORTAL_ESIGNET_CLIENT_ID": "solmara-portal",
        "PORTAL_ESIGNET_CLIENT_KEY_ID": "solmara-portal-key-1",
        "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64": local_rsa_private_key_b64(),
        "PORTAL_ESIGNET_ISSUER": "http://127.0.0.1:4308",
        "PORTAL_ESIGNET_AUTHORIZATION_ENDPOINT": "http://127.0.0.1:4309/authorize",
        "PORTAL_ESIGNET_TOKEN_ENDPOINT": "http://esignet:8088/v1/esignet/oauth/v2/token",
        "PORTAL_ESIGNET_CLIENT_ASSERTION_AUDIENCE": "http://127.0.0.1:4308/v1/esignet/oauth/v2/token",
        "PORTAL_ESIGNET_USERINFO_ENDPOINT": "http://esignet:8088/v1/esignet/oidc/userinfo",
        "PORTAL_ESIGNET_REDIRECT_URI": "http://127.0.0.1:4300/auth/callback",
        "PORTAL_ESIGNET_SCOPE": "openid profile",
        "PORTAL_ESIGNET_SUBJECT_CLAIM": "individual_id",
        "SOLMARA_ESIGNET_PUBLIC_BASE_URL": "http://127.0.0.1:4308",
        "SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL": "http://127.0.0.1:4309",
        "SOLMARA_POSTGRES_USER": postgres_user,
        "SOLMARA_POSTGRES_PASSWORD": postgres_password,
        "SOLMARA_POSTGRES_DB": postgres_db,
        "NIA_SOURCE_POSTGRES_READER_PASSWORD": nia_source_password,
        "SIPF_SOURCE_POSTGRES_READER_PASSWORD": sipf_source_password,
        "SOLMARA_NIA_DATABASE_URL": f"postgres://solmara_source_nia_reader:{nia_source_password}@postgres:5432/{postgres_db}?sslmode=require",
        "SOLMARA_SIPF_DATABASE_URL": f"postgres://solmara_source_sipf_reader:{sipf_source_password}@postgres:5432/{postgres_db}?sslmode=require",
        "SOLMARA_ESIGNET_POSTGRES_PASSWORD": raw_key(),
        "CHILD_BENEFIT_FEDERATOR_TOKEN": raw_key(),
        "CHILD_BENEFIT_FEDERATOR_URL": "http://127.0.0.1:4321",
        "CRA_NOTARY_URL": "http://127.0.0.1:4325",
        "NIA_NOTARY_URL": "http://127.0.0.1:4326",
        "SRO_NOTARY_URL": "http://127.0.0.1:4327",
        "PROGRAMME_NOTARY_URL": "http://127.0.0.1:4328",
        "SIPF_NOTARY_URL": "http://127.0.0.1:4322",
        "NAGDI_NOTARY_URL": "http://127.0.0.1:4323",
    }

    for raw_name, hash_name in RAW_HASH_PAIRS:
        raw = raw_key()
        values[raw_name] = raw
        values[hash_name] = fingerprint(raw)

    for name, kid in JWK_KIDS.items():
        values[name] = local_ed25519_jwk(kid)

    output = ROOT / ".env"
    write_env_file(
        output, values, "# Generated by scripts/gen-secrets.py. Do not commit."
    )
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
