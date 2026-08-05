#!/usr/bin/env python3
"""Smoke the running local Registry Evidence and Mint topology."""

from __future__ import annotations

import importlib
import os
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenarios.common import http_json, joined_url  # noqa: E402


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    module_name: str
    step_id: str
    expected_status: int | tuple[int, ...] | range
    expected_values: dict[str, bool]


SCENARIO_CASES = (
    ScenarioCase(
        "child eligible",
        "child_benefit",
        "positive",
        200,
        {
            "birth-is-registered": True,
            "population-record-active": True,
            "child-age-under-5": True,
            "household-below-poverty-threshold": True,
            "not-already-enrolled": True,
        },
    ),
    ScenarioCase("child deceased control", "child_benefit", "deceased-control", 200, {"child-age-under-5": False}),
    ScenarioCase("child poverty control", "child_benefit", "poverty-control", 200, {"household-below-poverty-threshold": False}),
    ScenarioCase("child unregistered control", "child_benefit", "unregistered-control", 200, {"birth-is-registered": False}),
    ScenarioCase("child duplicate control", "child_benefit", "duplicate-control", 200, {"not-already-enrolled": False}),
    ScenarioCase("child purpose denial", "child_benefit", "purpose-denial", range(400, 500), {}),
    ScenarioCase(
        "pension stop payment",
        "pension_survivor",
        "stop-payment",
        200,
        {"person-is-deceased": True, "pension-payment-active": True},
    ),
    ScenarioCase("pension stale death control", "pension_survivor", "stale-control", 200, {"person-is-deceased": False}),
    ScenarioCase("pension survivor benefit", "pension_survivor", "survivor-benefit", 200, {"survivor-is-eligible": True}),
    ScenarioCase("pension dissolved marriage control", "pension_survivor", "dissolved-control", 200, {"survivor-is-eligible": False}),
    ScenarioCase("pension over-disclosure denial", "pension_survivor", "cause-of-death-denial", range(400, 500), {}),
    ScenarioCase("farmer voucher eligible", "farmer_voucher", "positive", 200, {"eligible-for-climate-smart-input-voucher": True}),
    ScenarioCase("farmer authorization control", "farmer_voucher", "authorization-control", 200, {"eligible-for-climate-smart-input-voucher": False}),
    ScenarioCase("farmer redeemed control", "farmer_voucher", "redeemed-control", 200, {"eligible-for-climate-smart-input-voucher": False}),
    ScenarioCase("livestock movement eligible", "farmer_voucher", "movement-permit", 200, {"eligible-for-livestock-movement-permit": True}),
    ScenarioCase("livestock purpose denial", "farmer_voucher", "purpose-denial", range(400, 500), {}),
    ScenarioCase(
        "citizen self-service",
        "citizen",
        "positive",
        200,
        {"citizen-population-record-active": True, "civil-record-linked": True},
    ),
    ScenarioCase("citizen purpose denial", "citizen", "purpose-denial", range(400, 500), {}),
)


def main() -> int:
    load_dotenv(ROOT / ".env")
    failures = check_runtime()
    for case in SCENARIO_CASES:
        failures.extend(check_case(case))

    if failures:
        for failure in failures:
            print(f"smoke-live: {failure}", file=sys.stderr)
        return 1

    print(f"smoke-live: Mint, Evidence, and {len(SCENARIO_CASES)} scenario checks passed")
    return 0


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


def check_runtime() -> list[str]:
    evidence_url = os.environ.get("SOLMARA_EVIDENCE_URL", "https://localhost:4341")
    failures: list[str] = []
    readiness = wait_for_readiness(evidence_url)
    if readiness is not None:
        failures.append(readiness)

    metadata = http_json(
        "GET",
        joined_url(evidence_url, "/.well-known/oauth-authorization-server"),
        {"Accept": "application/json"},
        timeout=5.0,
    )
    if metadata.status != 200:
        failures.append(f"Mint metadata returned {metadata.status or metadata.error}; body={compact_body(metadata.body)}")
    elif not isinstance(metadata.body, dict) or metadata.body.get("issuer") != "https://mint.evidence.solmara.invalid":
        failures.append(f"Mint metadata exposed an unexpected issuer; body={compact_body(metadata.body)}")
    return failures


def wait_for_readiness(evidence_url: str) -> str | None:
    url = joined_url(evidence_url, "/ready")
    deadline = time.monotonic() + float(os.environ.get("SOLMARA_SMOKE_READY_TIMEOUT_SECONDS", "90"))
    last_status: int | None = None
    last_error = ""
    while time.monotonic() < deadline:
        result = http_json("GET", url, {}, timeout=2.0)
        last_status = result.status
        last_error = result.error
        if result.status in {200, 204}:
            return None
        time.sleep(1)
    detail = f"status {last_status}" if last_status is not None else last_error or "no response"
    return f"Evidence /ready did not become ready at {url} ({detail})"


def check_case(case: ScenarioCase) -> list[str]:
    module = importlib.import_module(f"scenarios.{case.module_name}")
    result = module.run_step({}, case.step_id)
    response = result.get("response_source", {})
    status = response.get("status")
    if not status_matches(status, case.expected_status):
        return [
            f"{case.name}: expected HTTP {format_expected(case.expected_status)}, got {status}; "
            f"body={compact_body(response.get('body'))}"
        ]
    if not case.expected_values:
        return []

    values = claim_values(response.get("body", {}))
    return [
        f"{case.name}: expected {claim_id}={expected}, got {values.get(claim_id)}; "
        f"body={compact_body(response.get('body'))}"
        for claim_id, expected in case.expected_values.items()
        if values.get(claim_id) is not expected
    ]


def status_matches(status: Any, expected: int | tuple[int, ...] | range) -> bool:
    if not isinstance(status, int):
        return False
    return status == expected if isinstance(expected, int) else status in expected


def format_expected(expected: int | tuple[int, ...] | range) -> str:
    if isinstance(expected, range):
        return f"{expected.start}-{expected.stop - 1}"
    if isinstance(expected, tuple):
        return ",".join(str(item) for item in expected)
    return str(expected)


def claim_values(body: Any) -> dict[str, bool | None]:
    if not isinstance(body, dict):
        return {}
    results = body.get("results", [])
    if not isinstance(results, list):
        return {}
    return {
        item["claim_id"]: item.get("value") if isinstance(item.get("value"), bool) else item.get("satisfied")
        for item in results
        if isinstance(item, dict) and isinstance(item.get("claim_id"), str)
    }


def compact_body(body: Any) -> str:
    text = str(body)
    return text if len(text) <= 500 else text[:497] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
