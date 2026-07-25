#!/usr/bin/env python3
"""Prove the NIA eSignet attribute-release profile against the live Relay."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


PURPOSE = "https://id.registrystack.org/solmara/purpose/esignet-identity-verification"
PROFILE_PATH = (
    "/v1/attribute-releases/solmara-nia-userinfo/versions/v1/resolve"
)
SUBJECT = "2300018263"


def main() -> int:
    token = os.environ.get("NIA_ESIGNET_RELAY_TOKEN", "")
    if not token:
        print(
            "smoke-nia-attribute-release: missing NIA_ESIGNET_RELAY_TOKEN",
            file=sys.stderr,
        )
        return 1

    base_url = os.environ.get("SOLMARA_NIA_RELAY_URL", "http://127.0.0.1:4312")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{PROFILE_PATH}",
        data=json.dumps(
            {"subject": {"id_type": "national_id", "value": SUBJECT}}
        ).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Data-Purpose": PURPOSE,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            status = response.status
            body = parse_json(response.read())
    except urllib.error.HTTPError as error:
        status = error.code
        body = parse_json(error.read())
    except Exception as error:
        print(
            "smoke-nia-attribute-release: request failed "
            f"({error.__class__.__name__})",
            file=sys.stderr,
        )
        return 1

    failure = validate_response(status, body)
    if failure:
        print(f"smoke-nia-attribute-release: {failure}", file=sys.stderr)
        return 1

    print(
        "smoke-nia-attribute-release: governed eSignet identity resolution passed"
    )
    return 0


def parse_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def validate_response(status: int, body: Any) -> str | None:
    if status != 200:
        code = body.get("code") if isinstance(body, dict) else None
        return f"expected HTTP 200, got {status}" + (f" {code}" if code else "")
    if not isinstance(body, dict):
        return "response was not a JSON object"
    if body.get("profile_id") != "solmara-nia-userinfo":
        return "response profile_id did not match"
    if body.get("profile_version") != "v1":
        return "response profile_version did not match"
    claims = body.get("claims")
    if not isinstance(claims, dict):
        return "response omitted the minimized claims object"
    if claims.get("individual_id") != SUBJECT or claims.get("name") != "Elena Dela Cruz":
        return "response claims did not match the synthetic eSignet subject"
    if "source" in body:
        return "response disclosed source metadata"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
