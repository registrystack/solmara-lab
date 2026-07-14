#!/usr/bin/env python3
"""Generate local .env credentials for Solmara Lab."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

from compose_project_name import compose_project_name

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_SSL_DIR = ROOT / "config" / "postgres" / "ssl"
CHILD_BENEFIT_PUBLIC_DOMAIN = os.environ.get("CHILD_BENEFIT_PUBLIC_DOMAIN", "lab.registrystack.org")

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
    ("CIVIL_CHILD_BENEFIT_NOTARY_TOKEN", "CIVIL_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("NIA_CHILD_BENEFIT_NOTARY_TOKEN", "NIA_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("SRO_CHILD_BENEFIT_NOTARY_TOKEN", "SRO_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("PROGRAMME_CHILD_BENEFIT_NOTARY_TOKEN", "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN_HASH"),
    ("PENSION_NOTARY_TOKEN", "PENSION_CLIENT_TOKEN_HASH"),
    ("NAGDI_NOTARY_TOKEN", "NAGDI_CLIENT_TOKEN_HASH"),
    ("PORTAL_CITIZEN_NOTARY_TOKEN", "CITIZEN_PORTAL_BFF_TOKEN_HASH"),
    ("PORTAL_RELAY_TOKEN", "PORTAL_RELAY_TOKEN_HASH"),
]

FEDERATION_JWK_KIDS = {
    "CHILD_BENEFIT_FEDERATOR_REQUEST_JWK": f"did:web:child-benefit-federator.{CHILD_BENEFIT_PUBLIC_DOMAIN}#request-key-1",
    "CIVIL_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK": f"did:web:civil-child-benefit-notary.{CHILD_BENEFIT_PUBLIC_DOMAIN}#federation-key-1",
    "NIA_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK": f"did:web:nia-child-benefit-notary.{CHILD_BENEFIT_PUBLIC_DOMAIN}#federation-key-1",
    "SRO_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK": f"did:web:sro-child-benefit-notary.{CHILD_BENEFIT_PUBLIC_DOMAIN}#federation-key-1",
    "PROGRAMME_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK": f"did:web:programme-child-benefit-notary.{CHILD_BENEFIT_PUBLIC_DOMAIN}#federation-key-1",
}

JWK_KIDS = {
    **FEDERATION_JWK_KIDS,
    "PENSION_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:pension#issuer-key-1",
    "NAGDI_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:nagdi#issuer-key-1",
    "CITIZEN_NOTARY_ISSUER_JWK": "did:web:id.registrystack.org:solmara:notary:citizen#issuer-key-1",
    "CITIZEN_ISSUER_NOTARY_ISSUER_JWK": "did:web:citizen-issuer-notary.solmara.registrystack.org#issuer-key-1",
    "CITIZEN_ISSUER_NOTARY_ACCESS_TOKEN_JWK": "did:web:citizen-issuer-notary.solmara.registrystack.org#access-token-key-1",
}


def raw_key() -> str:
    return secrets.token_urlsafe(32)


def fingerprint(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("ascii")).hexdigest()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_int(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return b64url(value.to_bytes(width, "big"))


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


def read_der_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    size = first & 0x7F
    length = int.from_bytes(data[offset : offset + size], "big")
    return length, offset + size


def read_der_tlv(data: bytes, offset: int, expected_tag: int | None = None) -> tuple[int, bytes, int]:
    tag = data[offset]
    if expected_tag is not None and tag != expected_tag:
        raise ValueError(f"expected ASN.1 tag {expected_tag:#x}, got {tag:#x}")
    length, value_offset = read_der_length(data, offset + 1)
    end = value_offset + length
    return tag, data[value_offset:end], end


def read_der_int(data: bytes, offset: int) -> tuple[int, int]:
    _, value, end = read_der_tlv(data, offset, 0x02)
    return int.from_bytes(value.lstrip(b"\x00"), "big"), end


def local_rsa_key_material(kid: str) -> tuple[str, str]:
    private_pem = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    private_der = subprocess.run(
        ["openssl", "rsa", "-traditional", "-outform", "DER"],
        input=private_pem,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    _, sequence, _ = read_der_tlv(private_der, 0, 0x30)
    offset = 0
    _, offset = read_der_int(sequence, offset)
    modulus, offset = read_der_int(sequence, offset)
    public_exponent, offset = read_der_int(sequence, offset)
    private_exponent, offset = read_der_int(sequence, offset)
    prime_p, offset = read_der_int(sequence, offset)
    prime_q, offset = read_der_int(sequence, offset)
    exponent_p, offset = read_der_int(sequence, offset)
    exponent_q, offset = read_der_int(sequence, offset)
    coefficient, _ = read_der_int(sequence, offset)
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": b64url_int(modulus),
        "e": b64url_int(public_exponent),
        "d": b64url_int(private_exponent),
        "p": b64url_int(prime_p),
        "q": b64url_int(prime_q),
        "dp": b64url_int(exponent_p),
        "dq": b64url_int(exponent_q),
        "qi": b64url_int(coefficient),
    }
    return base64.b64encode(private_pem).decode("ascii"), json.dumps(
        jwk,
        separators=(",", ":"),
        sort_keys=True,
    )


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


def federation_jwk_values() -> dict[str, str]:
    return {
        "CHILD_BENEFIT_PUBLIC_DOMAIN": CHILD_BENEFIT_PUBLIC_DOMAIN,
        **{name: local_ed25519_jwk(kid) for name, kid in FEDERATION_JWK_KIDS.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--federation-output",
        type=Path,
        metavar="PATH",
        help="write only fresh child-benefit federation JWKs to a new 0600 env file",
    )
    args = parser.parse_args(argv)
    if args.federation_output is not None:
        output = args.federation_output
        if output.exists():
            print(f"Refusing to overwrite existing federation key file: {output}", file=sys.stderr)
            return 1
        write_env_file(
            output,
            federation_jwk_values(),
            "# Generated federation JWKs. Upload to the named deployment apps, then securely delete this file.",
        )
        print(f"Wrote {output}")
        return 0

    ensure_postgres_tls()
    postgres_user = "solmara_registry"
    postgres_password = raw_key()
    postgres_db = "solmara_lab"
    citizen_issuer_esignet_private_key_b64, citizen_issuer_esignet_rp_jwk = local_rsa_key_material(
        "solmara-citizen-issuer-key-1"
    )
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
        "CITIZEN_ISSUER_ESIGNET_CLIENT_PRIVATE_KEY_B64": citizen_issuer_esignet_private_key_b64,
        "CITIZEN_ISSUER_ESIGNET_RP_JWK": citizen_issuer_esignet_rp_jwk,
        "SOLMARA_ESIGNET_PUBLIC_BASE_URL": "http://127.0.0.1:4308",
        "SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL": "http://127.0.0.1:4309",
        "SOLMARA_POSTGRES_USER": postgres_user,
        "SOLMARA_POSTGRES_PASSWORD": postgres_password,
        "SOLMARA_POSTGRES_DB": postgres_db,
        "SOLMARA_NIA_DATABASE_URL": f"postgres://{postgres_user}:{postgres_password}@postgres:5432/{postgres_db}?sslmode=require",
        "SOLMARA_ESIGNET_POSTGRES_PASSWORD": raw_key(),
        "CHILD_BENEFIT_FEDERATOR_TOKEN": raw_key(),
        "CHILD_BENEFIT_FEDERATOR_URL": "http://127.0.0.1:4321",
        "CHILD_BENEFIT_PUBLIC_DOMAIN": CHILD_BENEFIT_PUBLIC_DOMAIN,
        "CIVIL_CHILD_BENEFIT_NOTARY_URL": "http://127.0.0.1:4325",
        "NIA_CHILD_BENEFIT_NOTARY_URL": "http://127.0.0.1:4326",
        "SRO_CHILD_BENEFIT_NOTARY_URL": "http://127.0.0.1:4327",
        "PROGRAMME_CHILD_BENEFIT_NOTARY_URL": "http://127.0.0.1:4328",
        "PENSION_NOTARY_URL": "http://127.0.0.1:4322",
        "NAGDI_NOTARY_URL": "http://127.0.0.1:4323",
        "PORTAL_CITIZEN_NOTARY_URL": "http://127.0.0.1:4324",
        "PORTAL_CIVIL_RELAY_URL": "http://127.0.0.1:4311",
        "PORTAL_SOCIAL_RELAY_URL": "http://127.0.0.1:4313",
        "PORTAL_AGRI_RELAY_URL": "http://127.0.0.1:4316",
        "PORTAL_CERTS_RELAY_URL": "http://127.0.0.1:4311",
        "CIVIL_CHILD_BENEFIT_PAIRWISE_SECRET": raw_key(),
        "NIA_CHILD_BENEFIT_PAIRWISE_SECRET": raw_key(),
        "SRO_CHILD_BENEFIT_PAIRWISE_SECRET": raw_key(),
        "PROGRAMME_CHILD_BENEFIT_PAIRWISE_SECRET": raw_key(),
    }

    for raw_name, hash_name in RAW_HASH_PAIRS:
        raw = raw_key()
        values[raw_name] = raw
        values[hash_name] = fingerprint(raw)

    for name, kid in JWK_KIDS.items():
        values[name] = local_ed25519_jwk(kid)

    output = ROOT / ".env"
    write_env_file(output, values, "# Generated by scripts/gen-secrets.py. Do not commit.")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
