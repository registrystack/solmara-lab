#!/usr/bin/env python3
"""Register the portal through the native eSignet v2 private client API."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone


CLIENT_ID = os.environ.get("ESIGNET_CLIENT_ID", "solmara-portal")
CLIENT_KEY_ID = os.environ.get("ESIGNET_CLIENT_KEY_ID", "solmara-portal-key-1")
RELYING_PARTY_ID = os.environ.get("ESIGNET_RELYING_PARTY_ID", "solmara")
DEFAULT_CLIENT_CLAIMS = [
    "person_reference",
    "family_name",
    "name",
    "given_name",
    "gender",
    "birthdate",
]


def run(args: list[str], *, input_text: str | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        args,
        input=input_text,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


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


def public_jwk(private_key: Path) -> str:
    der = subprocess.check_output(
        ["openssl", "rsa", "-in", str(private_key), "-pubout", "-outform", "DER"],
        stderr=subprocess.DEVNULL,
    )
    _, spki, _ = read_der_tlv(der, 0, 0x30)
    _, _, offset = read_der_tlv(spki, 0, 0x30)
    _, bit_string, _ = read_der_tlv(spki, offset, 0x03)
    if bit_string[0] != 0:
        raise ValueError("unsupported subject public key bit string")
    _, rsa_public_key, _ = read_der_tlv(bit_string[1:], 0, 0x30)
    modulus, offset = read_der_int(rsa_public_key, 0)
    exponent, _ = read_der_int(rsa_public_key, offset)

    def b64url_int(value: int) -> str:
        width = max(1, (value.bit_length() + 7) // 8)
        raw = value.to_bytes(width, "big")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    jwk = {
        "kty": "RSA",
        "kid": CLIENT_KEY_ID,
        "use": "sig",
        "alg": "RS256",
        "n": b64url_int(modulus),
        "e": b64url_int(exponent),
    }
    return json.dumps(jwk, separators=(",", ":"))


def ensure_private_key() -> tuple[Path, str, str]:
    key_file = Path(os.environ.get("ESIGNET_CLIENT_PRIVATE_KEY_FILE", "/var/lib/esignet-seed/client-private.pem"))
    key_file.parent.mkdir(parents=True, exist_ok=True)
    encoded = os.environ.get("ESIGNET_CLIENT_PRIVATE_KEY_B64")
    if encoded:
        key_file.write_bytes(base64.b64decode(encoded))
        key_file.chmod(0o600)
    elif not key_file.exists():
        run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key_file)])
        key_file.chmod(0o600)
    jwk = public_jwk(key_file)
    key_hash = hashlib.sha256(jwk.encode("utf-8")).hexdigest()
    return key_file, jwk, key_hash


def default_redirect_uris() -> list[str]:
    return [
        "http://127.0.0.1:4300/auth/callback",
        "http://localhost:4300/auth/callback",
    ]


def redirect_uris() -> list[str]:
    raw = os.environ.get("ESIGNET_CLIENT_REDIRECT_URIS_JSON", json.dumps(default_redirect_uris(), separators=(",", ":")))
    value = json.loads(raw)
    if not isinstance(value, list) or not value or not all(isinstance(uri, str) for uri in value):
        raise ValueError("ESIGNET_CLIENT_REDIRECT_URIS_JSON must be a non-empty JSON string array")
    if os.environ.get("ESIGNET_REQUIRE_HTTPS_REDIRECTS") == "true":
        for uri in value:
            parsed = urlparse(uri)
            host = (parsed.hostname or "").lower()
            try:
                is_loopback = ip_address(host).is_loopback
            except ValueError:
                is_loopback = host == "localhost" or host.endswith(".localhost")
            if parsed.scheme != "https" or is_loopback:
                raise ValueError(f"hosted eSignet redirect URI must be public HTTPS: {uri}")
    return value


def client_request(jwk: str) -> dict:
    return {
        "clientId": CLIENT_ID,
        "clientName": "Solmara Portal",
        "clientNameLangMap": {"eng": "Solmara Portal"},
        "relyingPartyId": RELYING_PARTY_ID,
        "logoUri": "https://id.registrystack.org/solmara/logo.svg",
        "redirectUris": redirect_uris(),
        "userClaims": DEFAULT_CLIENT_CLAIMS,
        "authContextRefs": ["mosip:idp:acr:static-code"],
        "publicKey": json.loads(jwk),
        "grantTypes": ["authorization_code"],
        "clientAuthMethods": ["private_key_jwt"],
        "additionalConfig": {
            "userinfo_response_type": "JWS",
            "require_pkce": True,
            "pkce_required": True,

        },
    }


def admin_request(method: str, path: str, payload: dict | None = None) -> dict:
    origin = os.environ.get("ESIGNET_ADMIN_URL", "http://esignet:8080").rstrip("/")
    data = None if payload is None else json.dumps({
        "requestTime": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"), "request": payload,
    }).encode()
    request = Request(origin + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def registration_binding(jwk: str) -> dict[str, str]:
    public = json.loads(jwk)
    canonical = json.dumps(public, sort_keys=True, separators=(",", ":"))
    return {"client_id": CLIENT_ID, "relying_party_id": RELYING_PARTY_ID,
            "public_key_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def binding_path() -> Path:
    directory = Path(os.environ.get("ESIGNET_SEED_STATE_DIR", "/var/lib/esignet-seed/state"))
    identifier = hashlib.sha256(CLIENT_ID.encode()).hexdigest()
    return directory / f"{identifier}.json"


def require_registered_binding(jwk: str) -> None:
    path = binding_path()
    if not path.exists() or json.loads(path.read_text()) != registration_binding(jwk):
        raise RuntimeError("existing eSignet registration key or relying party cannot be verified; "
                           "configure a fresh ESIGNET_CLIENT_ID and a fresh signing key, updating both matching portal values")


def save_registered_binding(jwk: str) -> None:
    path = binding_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(registration_binding(jwk), sort_keys=True) + "\n")
    path.chmod(0o600)


def seed_esignet(jwk: str, key_hash: str = "") -> None:
    payload = client_request(jwk)
    deadline = time.monotonic() + 180
    while True:
        try:
            current = admin_request("GET", "/client-mgmt/client/" + CLIENT_ID)
            if (current.get("response") or {}).get("clientId") == CLIENT_ID:
                require_registered_binding(jwk)
                payload["status"] = "ACTIVE"
                result = admin_request("PUT", "/client-mgmt/client/" + CLIENT_ID, payload)
            else:
                current_errors = current.get("errors") or []
                if not current_errors or any(e.get("errorCode") != "invalid_client_id" for e in current_errors):
                    raise RuntimeError("private eSignet client lookup failed")
                result = admin_request("POST", "/client-mgmt/client", payload)
            break
        except HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError(f"private eSignet client API rejected registration (HTTP {exc.code})") from None
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for private eSignet client API") from None
            time.sleep(2)
        except (URLError, OSError):
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for private eSignet client API") from None
            time.sleep(2)
    errors = result.get("errors") or []
    if any(error.get("errorCode") == "duplicate_client_id" for error in errors):
        # Go's update API intentionally does not rotate the registered signing key.
        # A changed key needs an explicit new client registration.
        require_registered_binding(jwk)
        payload["status"] = "ACTIVE"
        result = admin_request("PUT", "/client-mgmt/client/" + CLIENT_ID, payload)
        errors = result.get("errors") or []
    if errors or (result.get("response") or {}).get("clientId") != CLIENT_ID:
        codes = ", ".join(str(error.get("errorCode", "unknown")) for error in errors)
        raise RuntimeError("eSignet client registration failed: " + codes)
    save_registered_binding(jwk)


def main() -> int:
    _, jwk, key_hash = ensure_private_key()
    seed_esignet(jwk, key_hash)
    account_source = os.environ.get("ESIGNET_ACCOUNT_SOURCE_LABEL", "BREG population access profile esignet-source")
    print(f"Seeded eSignet client {CLIENT_ID}.")
    print(f"BREG-backed account source: {account_source}.")
    print("Demo credentials are configured without being written to logs.")
    if os.environ.get("ESIGNET_SEED_STAY_READY") == "true":
        Path("/tmp/ready").write_text("ready\n", encoding="utf-8")
        while True:
            time.sleep(3600)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"seed-esignet.py: {exc}", file=sys.stderr)
        raise
