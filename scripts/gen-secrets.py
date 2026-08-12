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
EVIDENCE_LOCAL_DIR = ROOT / "config" / "evidence" / "local"

JWK_KIDS = {
    "CRA_RELAY_WORKLOAD_JWK": "solmara-cra-relay-workload-key-1",
    "NIA_RELAY_WORKLOAD_JWK": "solmara-nia-relay-workload-key-1",
    "NIA_ESIGNET_RELAY_WORKLOAD_JWK": "solmara-nia-esignet-relay-workload-key-1",
    "SRO_RELAY_WORKLOAD_JWK": "solmara-sro-relay-workload-key-1",
    "PROGRAMME_RELAY_WORKLOAD_JWK": "solmara-programme-relay-workload-key-1",
    "SIPF_RELAY_WORKLOAD_JWK": "solmara-sipf-relay-workload-key-1",
    "NAGDI_RELAY_WORKLOAD_JWK": "solmara-nagdi-relay-workload-key-1",
}


def raw_key() -> str:
    return secrets.token_urlsafe(32)


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


def local_p256_jwk() -> str:
    private_der = subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "EC",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-outform",
            "DER",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    details = subprocess.run(
        ["openssl", "pkey", "-inform", "DER", "-text", "-noout"],
        input=private_der,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.decode("ascii")
    private_key = openssl_key_component(details, "priv")
    public_key = openssl_key_component(details, "pub")
    if len(private_key) != 32 or len(public_key) != 65 or public_key[0] != 4:
        raise RuntimeError("OpenSSL did not return one P-256 private key")
    x = b64url(public_key[1:33])
    y = b64url(public_key[33:])
    thumbprint_input = json.dumps(
        {"crv": "P-256", "kty": "EC", "x": x, "y": y},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "kid": b64url(hashlib.sha256(thumbprint_input).digest()),
        "alg": "ES256",
        "x": x,
        "y": y,
        "d": b64url(private_key),
    }
    return json.dumps(jwk, separators=(",", ":"), sort_keys=True)


def openssl_key_component(details: str, name: str) -> bytes:
    lines = iter(details.splitlines())
    for line in lines:
        if line.strip() != f"{name}:":
            continue
        encoded: list[str] = []
        for component in lines:
            if not component.startswith((" ", "\t")):
                break
            encoded.append(component.strip().replace(":", ""))
        return bytes.fromhex("".join(encoded))
    raise RuntimeError(f"OpenSSL did not report the {name} component")


def public_jwk(private_jwk: str) -> dict[str, str]:
    jwk = json.loads(private_jwk)
    names = ("kty", "crv", "kid", "alg", "x", "y")
    return {key: jwk[key] for key in names if key in jwk}


def write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip("\n") + "\n")
    path.chmod(0o600)


def write_public(path: Path, value: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
    path.chmod(0o644)


def ensure_evidence_material() -> None:
    evidence_dir = EVIDENCE_LOCAL_DIR / "evidence"
    mint_dir = EVIDENCE_LOCAL_DIR / "mint"
    tls_dir = EVIDENCE_LOCAL_DIR / "tls"
    for directory in (evidence_dir, mint_dir / "clients", tls_dir):
        directory.mkdir(parents=True, exist_ok=True)

    private_paths = (
        evidence_dir / "audit-hmac-key",
        evidence_dir / "subject-binding-hmac-key",
        evidence_dir / "signing-p256-private-jwk",
        mint_dir / "signing.jwk",
        mint_dir / "audit-hmac-key",
        mint_dir / "client-private.jwk",
        tls_dir / "ca.key",
        tls_dir / "gateway.key",
    )
    public_paths = (
        evidence_dir / "signing-p256-public.jwk",
        mint_dir / "signing-public.jwk",
        mint_dir / "clients" / "solmara-demo.yaml",
        tls_dir / "ca.crt",
        tls_dir / "gateway.crt",
    )
    material_paths = (*private_paths, *public_paths)
    migrate_legacy_evidence_signing_material(evidence_dir, mint_dir, material_paths)
    present = tuple(path for path in material_paths if path.is_file())
    if len(present) == len(material_paths):
        for path in private_paths:
            path.chmod(0o600)
        for path in public_paths:
            path.chmod(0o644)
        render_evidence_service_configs(evidence_dir, mint_dir)
        return
    if present:
        missing = ", ".join(
            str(path.relative_to(EVIDENCE_LOCAL_DIR))
            for path in material_paths
            if not path.is_file()
        )
        raise SystemExit(
            "incomplete local Evidence material: "
            f"{missing}; run `just reset`, remove config/evidence/local/evidence, "
            "config/evidence/local/mint, and config/evidence/local/tls, then rerun "
            "`just gen-secrets`"
        )

    write_private(evidence_dir / "audit-hmac-key", raw_key())
    write_private(evidence_dir / "subject-binding-hmac-key", raw_key())
    evidence_signing_jwk = local_p256_jwk()
    write_private(evidence_dir / "signing-p256-private-jwk", evidence_signing_jwk)
    write_public(
        evidence_dir / "signing-p256-public.jwk",
        public_jwk(evidence_signing_jwk),
    )

    mint_signing_jwk = local_p256_jwk()
    client_jwk = local_ed25519_jwk("solmara-demo-client-key-1")
    write_private(mint_dir / "signing.jwk", mint_signing_jwk)
    write_public(mint_dir / "signing-public.jwk", public_jwk(mint_signing_jwk))
    write_private(mint_dir / "audit-hmac-key", raw_key())
    write_private(mint_dir / "client-private.jwk", client_jwk)
    client = {
        "clientId": "solmara-demo",
        "principal": "https://id.registrystack.org/solmara/principal/demo-client",
        "evidenceAudience": "https://id.registrystack.org/solmara/audience/demo-client",
        "requesterTags": ["solmara-demo"],
        "keys": [public_jwk(client_jwk)],
    }
    client_path = mint_dir / "clients" / "solmara-demo.yaml"
    client_path.write_text(json.dumps(client, indent=2, sort_keys=True) + "\n")
    client_path.chmod(0o644)

    ca_certificate = tls_dir / "ca.crt"
    ca_private_key = tls_dir / "ca.key"
    certificate = tls_dir / "gateway.crt"
    private_key = tls_dir / "gateway.key"
    certificate_request = tls_dir / "gateway.csr"
    ca_serial = tls_dir / "ca.srl"
    for path in (
        ca_certificate,
        ca_private_key,
        certificate,
        private_key,
        certificate_request,
        ca_serial,
    ):
        path.unlink(missing_ok=True)
    san_names = [
        "localhost",
        "mint.evidence.solmara.invalid",
        "evidence.solmara.invalid",
        "cra-relay.evidence.solmara.invalid",
        "nia-relay.evidence.solmara.invalid",
        "sro-relay.evidence.solmara.invalid",
        "programme-relay.evidence.solmara.invalid",
        "sipf-relay.evidence.solmara.invalid",
        "nagdi-relay.evidence.solmara.invalid",
    ]
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "3650",
            "-subj",
            "/CN=Solmara Lab Evidence Development CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-keyout",
            str(ca_private_key),
            "-out",
            str(ca_certificate),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=evidence.solmara.invalid",
            "-addext",
            "subjectAltName=" + ",".join(f"DNS:{name}" for name in san_names),
            "-addext",
            "basicConstraints=critical,CA:FALSE",
            "-addext",
            "keyUsage=critical,digitalSignature,keyEncipherment",
            "-addext",
            "extendedKeyUsage=serverAuth",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate_request),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(certificate_request),
            "-CA",
            str(ca_certificate),
            "-CAkey",
            str(ca_private_key),
            "-CAcreateserial",
            "-days",
            "3650",
            "-copy_extensions",
            "copy",
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    certificate_request.unlink()
    ca_serial.unlink(missing_ok=True)
    ca_private_key.chmod(0o600)
    private_key.chmod(0o600)
    ca_certificate.chmod(0o644)
    certificate.chmod(0o644)
    render_evidence_service_configs(evidence_dir, mint_dir)


def render_evidence_service_configs(evidence_dir: Path, mint_dir: Path) -> None:
    configurations = (
        (
            ROOT / "evidence/bundle/evidence.yaml",
            evidence_dir / "evidence.yaml",
            evidence_dir / "signing-p256-public.jwk",
        ),
        (
            ROOT / "evidence/mint.yaml",
            mint_dir / "mint.yaml",
            mint_dir / "signing-public.jwk",
        ),
    )
    for template, destination, public_source in configurations:
        public = json.loads(public_source.read_text())
        kid = public.get("kid")
        if not isinstance(kid, str) or len(kid) != 43:
            raise RuntimeError("service public JWK does not have one thumbprint kid")
        public_directory = destination.parent / "public-keys"
        public_directory.mkdir(parents=True, exist_ok=True)
        for previous in public_directory.glob("*.jwk.json"):
            previous.unlink()
        write_public(public_directory / f"{kid}.jwk.json", public)

        rendered = template.read_text().replace(
            "public-keys/active.jwk.json", f"public-keys/{kid}.jwk.json"
        )
        if rendered == template.read_text():
            raise RuntimeError(
                f"{template} does not name the generated public key placeholder"
            )
        destination.write_text(rendered)
        destination.chmod(0o644)


def migrate_legacy_evidence_signing_material(
    evidence_dir: Path, mint_dir: Path, material_paths: tuple[Path, ...]
) -> None:
    legacy_evidence_signing = evidence_dir / "signing-ed25519-private-jwk"
    replacement_paths = {
        evidence_dir / "signing-p256-private-jwk",
        evidence_dir / "signing-p256-public.jwk",
        mint_dir / "signing-public.jwk",
    }
    legacy_paths = tuple(
        legacy_evidence_signing
        if path == evidence_dir / "signing-p256-private-jwk"
        else path
        for path in material_paths
        if path not in replacement_paths - {evidence_dir / "signing-p256-private-jwk"}
    )
    if not all(path.is_file() for path in legacy_paths) or any(
        path.exists() for path in replacement_paths
    ):
        return

    try:
        evidence_legacy = json.loads(legacy_evidence_signing.read_text())
        mint_legacy = json.loads((mint_dir / "signing.jwk").read_text())
    except (OSError, json.JSONDecodeError):
        return
    if any(
        jwk.get("alg") != "EdDSA" or "d" not in jwk
        for jwk in (evidence_legacy, mint_legacy)
    ):
        return

    evidence_signing_jwk = local_p256_jwk()
    mint_signing_jwk = local_p256_jwk()
    write_private(evidence_dir / "signing-p256-private-jwk", evidence_signing_jwk)
    write_public(
        evidence_dir / "signing-p256-public.jwk",
        public_jwk(evidence_signing_jwk),
    )
    write_private(mint_dir / "signing.jwk", mint_signing_jwk)
    write_public(mint_dir / "signing-public.jwk", public_jwk(mint_signing_jwk))
    legacy_evidence_signing.unlink()
    print("rotated local Evidence and Mint service signing keys from EdDSA to ES256")


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
    ensure_evidence_material()
    postgres_user = "solmara_registry"
    postgres_password = raw_key()
    postgres_db = "solmara_lab"
    nia_source_password = raw_key()
    sipf_source_password = raw_key()
    values: dict[str, str] = {
        "COMPOSE_PROJECT_NAME": compose_project_name(ROOT),
        "CRA_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "NIA_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "SRO_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "PROGRAMME_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "SIPF_RELAY_AUDIT_HASH_SECRET": raw_key(),
        "NAGDI_RELAY_AUDIT_HASH_SECRET": raw_key(),
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
        "CHILD_BENEFIT_FEDERATOR_URL": "https://localhost:4341/child-benefit/",
        # Host-side scenario smokes use the gateway's localhost certificate SAN.
        # Compose services override these with the internal gateway hostnames.
        "SOLMARA_EVIDENCE_URL": "https://localhost:4341",
        "SOLMARA_MINT_URL": "https://localhost:4341",
        "SOLMARA_MINT_ASSERTION_AUDIENCE": "https://mint.evidence.solmara.invalid/token",
        "SOLMARA_EVIDENCE_CLIENT_ID": "solmara-demo",
        "SOLMARA_EVIDENCE_CLIENT_KEY": str(
            ROOT / "config/evidence/local/mint/client-private.jwk"
        ),
        "SOLMARA_EVIDENCE_CA_BUNDLE": str(ROOT / "config/evidence/local/tls/ca.crt"),
    }

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
