#!/usr/bin/env python3
"""Generate local .env credentials for Solmara Lab."""

from __future__ import annotations

import hashlib
import json
import base64
import secrets
import shlex
import subprocess
from pathlib import Path

from compose_project_name import compose_project_name

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_SSL_DIR = ROOT / "config" / "postgres" / "ssl"

RAW_HASH_PAIRS = [
    ("CRA_CHILD_BENEFIT_SOURCE_RAW", "CRA_CHILD_BENEFIT_SOURCE_HASH"),
    ("CRA_PENSION_SOURCE_RAW", "CRA_PENSION_SOURCE_HASH"),
    ("CRA_CITIZEN_SOURCE_RAW", "CRA_CITIZEN_SOURCE_HASH"),
    ("NIA_CHILD_BENEFIT_SOURCE_RAW", "NIA_CHILD_BENEFIT_SOURCE_HASH"),
    ("NIA_PENSION_SOURCE_RAW", "NIA_PENSION_SOURCE_HASH"),
    ("NIA_CITIZEN_SOURCE_RAW", "NIA_CITIZEN_SOURCE_HASH"),
    ("SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW", "SOLMARA_ESIGNET_IDENTITY_RELEASE_HASH"),
    ("SRO_CHILD_BENEFIT_SOURCE_RAW", "SRO_CHILD_BENEFIT_SOURCE_HASH"),
    ("SRO_CITIZEN_SOURCE_RAW", "SRO_CITIZEN_SOURCE_HASH"),
    ("PROGRAMME_CHILD_BENEFIT_SOURCE_RAW", "PROGRAMME_CHILD_BENEFIT_SOURCE_HASH"),
    ("PROGRAMME_PENSION_SOURCE_RAW", "PROGRAMME_PENSION_SOURCE_HASH"),
    ("PROGRAMME_CITIZEN_SOURCE_RAW", "PROGRAMME_CITIZEN_SOURCE_HASH"),
    ("SIPF_PENSION_SOURCE_RAW", "SIPF_PENSION_SOURCE_HASH"),
    ("SIPF_CITIZEN_SOURCE_RAW", "SIPF_CITIZEN_SOURCE_HASH"),
    ("NAGDI_NOTARY_SOURCE_RAW", "NAGDI_NOTARY_SOURCE_HASH"),
    ("NAGDI_CITIZEN_SOURCE_RAW", "NAGDI_CITIZEN_SOURCE_HASH"),
    ("CHILD_BENEFIT_NOTARY_TOKEN", "CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("PENSION_NOTARY_TOKEN", "PENSION_CLIENT_TOKEN_HASH"),
    ("NAGDI_NOTARY_TOKEN", "NAGDI_CLIENT_TOKEN_HASH"),
    ("PORTAL_CITIZEN_NOTARY_TOKEN", "CITIZEN_PORTAL_BFF_TOKEN_HASH"),
    ("PORTAL_RELAY_TOKEN", "PORTAL_RELAY_TOKEN_HASH"),
]

JWK_KIDS = {
    "CHILD_BENEFIT_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:child-benefit#issuer-key-1",
    "PENSION_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:pension#issuer-key-1",
    "NAGDI_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:nagdi#issuer-key-1",
    "CITIZEN_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:citizen#issuer-key-1",
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


def main() -> int:
    ensure_postgres_tls()
    postgres_user = "solmara_registry"
    postgres_password = raw_key()
    postgres_db = "solmara_lab"
    values: dict[str, str] = {
        "COMPOSE_PROJECT_NAME": compose_project_name(ROOT),
        "REGISTRY_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "REGISTRY_NOTARY_AUDIT_HASH_SECRET": raw_key(),
        "REGISTRY_NOTARY_REPLAY_REDIS_URL": "redis://redis:6379/0",
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
        "SOLMARA_NIA_DATABASE_URL": f"postgres://{postgres_user}:{postgres_password}@postgres:5432/{postgres_db}?sslmode=require",
        "SOLMARA_ESIGNET_POSTGRES_PASSWORD": raw_key(),
        "CHILD_BENEFIT_NOTARY_URL": "http://127.0.0.1:4321",
        "PENSION_NOTARY_URL": "http://127.0.0.1:4322",
        "NAGDI_NOTARY_URL": "http://127.0.0.1:4323",
        "PORTAL_CITIZEN_NOTARY_URL": "http://127.0.0.1:4324",
        "PORTAL_CIVIL_RELAY_URL": "http://127.0.0.1:4311",
        "PORTAL_SOCIAL_RELAY_URL": "http://127.0.0.1:4313",
        "PORTAL_AGRI_RELAY_URL": "http://127.0.0.1:4316",
        "PORTAL_CERTS_RELAY_URL": "http://127.0.0.1:4311",
    }

    for raw_name, hash_name in RAW_HASH_PAIRS:
        raw = raw_key()
        values[raw_name] = raw
        values[hash_name] = fingerprint(raw)

    for name, kid in JWK_KIDS.items():
        values[name] = local_ed25519_jwk(kid)

    output = ROOT / ".env"
    lines = [
        "# Generated by scripts/gen-secrets.py. Do not commit.",
        *[env_line(key, values[key]) for key in sorted(values)],
    ]
    output.write_text("\n".join(lines) + "\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
