#!/usr/bin/env python3
"""Smoke checks for Solmara eSignet and its NIA attribute-release backend."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PURPOSE = "https://id.registrystack.org/solmara/purpose/esignet-identity-verification"
PROFILE_ID = "solmara-nia-userinfo"
PROFILE_VERSION = "v1"
DEFAULT_CLAIMS = ["individual_id", "name", "given_name", "family_name", "birthdate", "gender"]
DEFAULT_EXPECTED_UIN = "2300018263"
POPULATION_FIXTURE = ROOT / "ministries" / "interior-population" / "fixtures" / "population_person.csv"


@dataclass(frozen=True)
class SmokeTargets:
    relay_url: str
    esignet_url: str
    esignet_ui_url: str


class SmokeFailure(Exception):
    """Stable operator-facing smoke failure."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = {**load_env_file(args.env_file), **os.environ}
    targets = SmokeTargets(
        relay_url=normalize_url(args.relay_url or env.get("SOLMARA_NIA_RELAY_URL") or "http://127.0.0.1:4312"),
        esignet_url=normalize_url(args.esignet_url or env.get("SOLMARA_ESIGNET_PUBLIC_BASE_URL") or "http://127.0.0.1:4308"),
        esignet_ui_url=normalize_url(
            args.esignet_ui_url or env.get("SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL") or "http://127.0.0.1:4309"
        ),
    )
    token = env.get("SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW")
    if not token:
        print("FAILED: SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW is required; run just gen-secrets", file=sys.stderr)
        return 1
    expected_uin = args.expected_uin
    subject = args.subject or default_legacy_nid(expected_uin)

    checks: list[tuple[str, Any]] = [
        ("eSignet service discovery", lambda: check_esignet_discovery(targets, args.timeout)),
        (
            "NIA UserInfo attribute release",
            lambda: check_attribute_release(targets, token, subject, expected_uin, args.timeout),
        ),
    ]
    for name, check in checks:
        print(f"check: {name}", flush=True)
        try:
            check()
        except SmokeFailure as exc:
            print(f"FAILED: {name}: {exc}", file=sys.stderr)
            return 1
    print("smoke-esignet: eSignet backend smoke passed")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="local env file, default .env")
    parser.add_argument("--relay-url", help="NIA Relay base URL, default SOLMARA_NIA_RELAY_URL or local port")
    parser.add_argument("--esignet-url", help="eSignet service public base URL, default local port")
    parser.add_argument("--esignet-ui-url", help="eSignet UI public base URL, default local port")
    parser.add_argument("--subject", help="legacy national ID to resolve, default is read from the population fixture")
    parser.add_argument("--expected-uin", default=DEFAULT_EXPECTED_UIN, help="expected Solmara UIN for the demo subject")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for each endpoint")
    return parser.parse_args(argv[1:] if argv[:1] == ["--"] else argv)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        try:
            parsed = shlex.split(value, posix=True)
        except ValueError:
            parsed = [value]
        values[key] = parsed[0] if parsed else ""
    return values


def normalize_url(value: str) -> str:
    return value.rstrip("/")


def default_legacy_nid(expected_uin: str) -> str:
    with POPULATION_FIXTURE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("uin") == expected_uin:
                legacy_nid = row.get("legacy_nid")
                if legacy_nid:
                    return legacy_nid
    raise SmokeFailure(f"could not find legacy_nid for UIN {expected_uin}")


def check_esignet_discovery(targets: SmokeTargets, timeout: float) -> None:
    service_doc = wait_for_json(
        "GET",
        f"{targets.esignet_url}/v1/esignet/oidc/.well-known/openid-configuration",
        timeout=timeout,
    )
    ui_doc = wait_for_json("GET", f"{targets.esignet_ui_url}/.well-known/openid-configuration", timeout=timeout)
    service_issuer = service_doc.get("issuer")
    ui_issuer = ui_doc.get("issuer")
    if not isinstance(service_issuer, str) or not service_issuer:
        raise SmokeFailure("service discovery omitted issuer")
    if ui_issuer != service_issuer:
        raise SmokeFailure("UI discovery issuer does not match service discovery issuer")


def check_attribute_release(
    targets: SmokeTargets,
    token: str,
    subject: str,
    expected_uin: str,
    timeout: float,
) -> None:
    body = {
        "subject": {"id_type": "national_id", "value": subject},
        "claims": DEFAULT_CLAIMS,
    }
    response = wait_for_json(
        "POST",
        f"{targets.relay_url}/v1/attribute-releases/{PROFILE_ID}/versions/{PROFILE_VERSION}/resolve",
        timeout=timeout,
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "data-purpose": PURPOSE,
        },
        body=body,
    )
    claims = response.get("claims")
    if not isinstance(claims, dict):
        raise SmokeFailure("attribute release response omitted claims")
    if claims.get("individual_id") != expected_uin:
        raise SmokeFailure("attribute release returned the wrong individual_id")
    if claims.get("name") != "Elena Dela Cruz":
        raise SmokeFailure("attribute release returned the wrong name")


def wait_for_json(
    method: str,
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            return request_json(method, url, headers=headers, body=body)
        except SmokeFailure as exc:
            last_error = str(exc)
        time.sleep(1)
    raise SmokeFailure(f"{url}: {last_error or 'timed out'}")


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=payload, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
            value = json.loads(data.decode("utf-8"))
            if not isinstance(value, dict):
                raise SmokeFailure("response was not a JSON object")
            return value
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        raise SmokeFailure(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SmokeFailure(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
