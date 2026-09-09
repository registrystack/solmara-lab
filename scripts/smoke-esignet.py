#!/usr/bin/env python3
"""Smoke checks for the public Solmara eSignet discovery surfaces."""

from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class SmokeTargets:
    esignet_url: str
    esignet_ui_url: str


class SmokeFailure(Exception):
    """Stable operator-facing smoke failure."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = {**load_env_file(args.env_file), **os.environ}
    targets = SmokeTargets(
        esignet_url=normalize_url(
            args.esignet_url
            or env.get("SOLMARA_ESIGNET_PUBLIC_BASE_URL")
            or "http://127.0.0.1:4308"
        ),
        esignet_ui_url=normalize_url(
            args.esignet_ui_url
            or env.get("SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL")
            or "http://127.0.0.1:4309"
        ),
    )
    checks: list[tuple[str, Any]] = [
        (
            "eSignet service discovery",
            lambda: check_esignet_discovery(targets, args.timeout),
        ),
    ]
    for name, check in checks:
        print(f"check: {name}", flush=True)
        try:
            check()
        except SmokeFailure as exc:
            print(f"FAILED: {name}: {exc}", file=sys.stderr)
            return 1
    print("smoke-esignet: eSignet discovery smoke passed")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / ".env",
        help="local env file, default .env",
    )
    parser.add_argument(
        "--esignet-url", help="eSignet service public base URL, default local port"
    )
    parser.add_argument(
        "--esignet-ui-url", help="eSignet UI public base URL, default local port"
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="seconds to wait for each endpoint"
    )
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


def check_esignet_discovery(targets: SmokeTargets, timeout: float) -> None:
    oidc = wait_for_json(
        "GET", f"{targets.esignet_url}/.well-known/openid-configuration", timeout=timeout
    )
    oauth = wait_for_json(
        "GET", f"{targets.esignet_url}/.well-known/oauth-authorization-server", timeout=timeout
    )
    ui = wait_for_json(
        "GET", f"{targets.esignet_ui_url}/.well-known/openid-configuration", timeout=timeout
    )
    expected = {
        "issuer": targets.esignet_url,
        "authorization_endpoint": f"{targets.esignet_url}/oauth2/authorize",
        "token_endpoint": f"{targets.esignet_url}/oauth2/token",
        "jwks_uri": f"{targets.esignet_url}/oauth2/jwks",
    }
    for document in (oidc, oauth, ui):
        for key, value in expected.items():
            if document.get(key) != value:
                raise SmokeFailure(f"discovery {key} does not match the public eSignet endpoint")
        if "private_key_jwt" not in document.get("token_endpoint_auth_methods_supported", []):
            raise SmokeFailure("discovery does not support private_key_jwt")
    for document in (oidc, ui):
        if document.get("userinfo_endpoint") != f"{targets.esignet_url}/oauth2/userinfo":
            raise SmokeFailure("discovery userinfo_endpoint does not match the public eSignet endpoint")


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
    raise SmokeFailure(last_error or "endpoint timed out")


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=payload, method=method, headers=headers or {}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise SmokeFailure("discovery response exceeded limit")
            value = json.loads(data.decode("utf-8"))
            if not isinstance(value, dict):
                raise SmokeFailure("response was not a JSON object")
            return value
    except urllib.error.HTTPError as exc:
        raise SmokeFailure(f"discovery HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeFailure("discovery response unavailable or invalid") from None


if __name__ == "__main__":
    raise SystemExit(main())
