#!/usr/bin/env python3
"""Probe Relay readiness and the private consultation boundary.

Authority Notaries reach their paired Relays with short-lived workload
identity tokens. This smoke deliberately has no such token: it proves that all
six Relays are ready while direct access to a private consultation profile is
refused with the stable invalid-credentials problem.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "smoke" / "relay-sources.json"
HttpResult = tuple[int | None, dict[str, str], Any, str]
RelayReadiness = tuple[HttpResult, HttpResult]


@dataclass(frozen=True)
class RelayBoundary:
    name: str
    base_url_env: str
    default_base_url: str
    consultation_profile: str


RELAYS = (
    RelayBoundary(
        "CRA Relay",
        "SOLMARA_CRA_RELAY_URL",
        "http://127.0.0.1:4311",
        "solmara-cra-civil.cra-child-benefit.civil",
    ),
    RelayBoundary(
        "NIA Relay",
        "SOLMARA_NIA_RELAY_URL",
        "http://127.0.0.1:4312",
        "solmara-nia-population.nia-child-benefit.population",
    ),
    RelayBoundary(
        "SRO Relay",
        "SOLMARA_SRO_RELAY_URL",
        "http://127.0.0.1:4313",
        "solmara-sro-social.child-benefit.household",
    ),
    RelayBoundary(
        "Programme Relay",
        "SOLMARA_PROGRAMME_RELAY_URL",
        "http://127.0.0.1:4314",
        "solmara-mosd-programme.child-benefit.enrollment",
    ),
    RelayBoundary(
        "SIPF Relay",
        "SOLMARA_SIPF_RELAY_URL",
        "http://127.0.0.1:4315",
        "solmara-sipf-pensions.sipf-pension-payment-review.pension",
    ),
    RelayBoundary(
        "NAgDI Relay",
        "SOLMARA_NAGDI_RELAY_URL",
        "http://127.0.0.1:4316",
        "solmara-nagdi-agriculture.voucher.farmer",
    ),
)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    readiness = wait_for_relays()

    for relay in RELAYS:
        result = run_probe(relay, *readiness[relay.name])
        results.append(result)
        if result["status"] != "ok":
            failures.append(
                f"{relay.name}: {result['status']} ({result.get('detail', 'no detail')})"
            )

    OUTPUT.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if failures:
        for failure in failures:
            print(f"smoke-relay-sources: {failure}", file=sys.stderr)
        print(
            f"smoke-relay-sources: wrote {OUTPUT.relative_to(ROOT)}", file=sys.stderr
        )
        return 1

    print(
        f"smoke-relay-sources: {len(RELAYS)} Relay readiness and private-consultation denial checks passed; "
        f"wrote {OUTPUT.relative_to(ROOT)}"
    )
    return 0


def wait_for_relays() -> dict[str, RelayReadiness]:
    deadline = time.monotonic() + float(
        os.environ.get("SOLMARA_SMOKE_READY_TIMEOUT_SECONDS", "90")
    )
    latest: dict[str, RelayReadiness] = {}
    while True:
        for relay in RELAYS:
            base_url = os.environ.get(relay.base_url_env, relay.default_base_url)
            latest[relay.name] = (
                http_get(joined_url(base_url, "/healthz")),
                http_get(joined_url(base_url, "/ready")),
            )
        if all(
            health[0] == 200 and ready[0] == 200
            for health, ready in latest.values()
        ) or time.monotonic() >= deadline:
            return latest
        time.sleep(1)


def run_probe(
    relay: RelayBoundary,
    health: HttpResult,
    ready: HttpResult,
) -> dict[str, Any]:
    base_url = os.environ.get(relay.base_url_env, relay.default_base_url)
    if health[0] != 200:
        return {
            "name": relay.name,
            "status": "health_unavailable",
            "detail": status_detail(health),
        }

    if ready[0] != 200:
        return {
            "name": relay.name,
            "status": "not_ready",
            "detail": status_detail(ready),
        }

    profile = urllib.parse.quote(relay.consultation_profile, safe=".-_")
    denial = http_get(joined_url(base_url, f"/v1/consultations/{profile}"))
    denial_failure = validate_unauthenticated_denial(denial)
    if denial_failure:
        return {
            "name": relay.name,
            "status": "consultation_boundary_failed",
            "detail": denial_failure,
        }

    return {
        "name": relay.name,
        "status": "ok",
        "liveness_status": health[0],
        "readiness_status": ready[0],
        "unauthenticated_consultation_status": denial[0],
        "unauthenticated_consultation_code": "auth.invalid_credentials",
    }


def http_get(url: str) -> HttpResult:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json"}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                parse_json(response.read()),
                "",
            )
    except urllib.error.HTTPError as error:
        return (
            error.code,
            {key.lower(): value for key, value in error.headers.items()},
            parse_json(error.read()),
            "",
        )
    except Exception as error:
        return None, {}, {}, error.__class__.__name__


def validate_unauthenticated_denial(
    response: HttpResult,
) -> str | None:
    status, headers, body, error = response
    if status != 401:
        return f"expected HTTP 401, got {status or error}"
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/problem+json":
        return f"expected application/problem+json, got {content_type or 'no content type'}"
    code = body.get("code") if isinstance(body, dict) else None
    if code != "auth.invalid_credentials":
        return f"expected auth.invalid_credentials, got {code!r}"
    if isinstance(body, dict) and any(
        key in body for key in ("data", "outputs", "results", "source_record")
    ):
        return "unauthenticated denial included source-shaped data"
    return None


def joined_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def parse_json(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"unparsed": raw.decode("utf-8", errors="replace")[:200]}


def status_detail(response: HttpResult) -> str:
    status, _, body, error = response
    if status is None:
        return error or "no response"
    code = body.get("code") if isinstance(body, dict) else None
    return f"HTTP {status}" + (f" {code}" if code else "")


if __name__ == "__main__":
    raise SystemExit(main())
