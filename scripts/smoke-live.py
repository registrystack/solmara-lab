#!/usr/bin/env python3
"""Smoke the running Solmara Lab Notary topology."""

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

from scenarios.common import CLAIM_RESULT_FORMAT, PURPOSES, auth_headers, env_url, http_json, joined_url  # noqa: E402


@dataclass(frozen=True)
class NotaryService:
    name: str
    url_env: str
    default_url: str
    token_env: str
    purpose: str
    claim_ids: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    module_name: str
    step_id: str
    expected_status: int | tuple[int, ...] | range
    expected_values: dict[str, bool]


SERVICES = (
    NotaryService(
        "Child Benefit Notary",
        "CHILD_BENEFIT_NOTARY_URL",
        "http://127.0.0.1:4321",
        "CHILD_BENEFIT_NOTARY_TOKEN",
        PURPOSES["child_benefit"],
        (
            "birth-is-registered",
            "child-age-under-5",
            "household-below-poverty-threshold",
            "not-already-enrolled",
            "eligible-for-child-benefit",
        ),
    ),
    NotaryService(
        "Pension Notary",
        "PENSION_NOTARY_URL",
        "http://127.0.0.1:4322",
        "PENSION_NOTARY_TOKEN",
        PURPOSES["pension_payment"],
        ("person-is-deceased", "pension-payment-should-stop", "survivor-is-eligible"),
    ),
    NotaryService(
        "NAgDI Notary",
        "NAGDI_NOTARY_URL",
        "http://127.0.0.1:4323",
        "NAGDI_NOTARY_TOKEN",
        PURPOSES["voucher"],
        (
            "farmer-registered",
            "data-use-authorized-for-purpose",
            "eligible-for-climate-smart-input-voucher",
            "registered-herd",
            "origin-district-not-quarantined-for-species",
            "eligible-for-livestock-movement-permit",
        ),
    ),
    NotaryService(
        "Citizen Notary",
        "PORTAL_CITIZEN_NOTARY_URL",
        "http://127.0.0.1:4324",
        "PORTAL_CITIZEN_NOTARY_TOKEN",
        "https://id.registrystack.org/solmara/purpose/citizen-self-service",
        ("population-record-active", "civil-record-linked", "citizen-self-service-summary"),
    ),
)

SCENARIO_CASES = (
    ScenarioCase(
        "child eligible",
        "child_benefit",
        "positive",
        200,
        {
            "birth-is-registered": True,
            "child-age-under-5": True,
            "household-below-poverty-threshold": True,
            "not-already-enrolled": True,
        },
    ),
    ScenarioCase(
        "child deceased control",
        "child_benefit",
        "deceased-control",
        200,
        {"child-age-under-5": False},
    ),
    ScenarioCase(
        "child poverty control",
        "child_benefit",
        "poverty-control",
        200,
        {"household-below-poverty-threshold": False},
    ),
    ScenarioCase("child unregistered control", "child_benefit", "unregistered-control", range(400, 500), {}),
    ScenarioCase(
        "child duplicate enrollment control",
        "child_benefit",
        "duplicate-control",
        200,
        {"not-already-enrolled": False},
    ),
    ScenarioCase("child unsupported purpose denial", "child_benefit", "purpose-denial", range(400, 500), {}),
    ScenarioCase(
        "pension stop payment",
        "pension_survivor",
        "stop-payment",
        200,
        {"person-is-deceased": True, "pension-payment-should-stop": True},
    ),
    ScenarioCase(
        "pension stale death control",
        "pension_survivor",
        "stale-control",
        200,
        {"person-is-deceased": False},
    ),
    ScenarioCase(
        "pension survivor benefit",
        "pension_survivor",
        "survivor-benefit",
        200,
        {"survivor-is-eligible": True},
    ),
    ScenarioCase("pension dissolved marriage control", "pension_survivor", "dissolved-control", range(400, 500), {}),
    ScenarioCase("pension over-disclosure denial", "pension_survivor", "cause-of-death-denial", range(400, 500), {}),
    ScenarioCase(
        "farmer voucher eligible",
        "farmer_voucher",
        "positive",
        200,
        {"eligible-for-climate-smart-input-voucher": True},
    ),
    ScenarioCase(
        "farmer missing authorization control",
        "farmer_voucher",
        "authorization-control",
        200,
        {"eligible-for-climate-smart-input-voucher": False},
    ),
    ScenarioCase(
        "farmer redeemed control",
        "farmer_voucher",
        "redeemed-control",
        200,
        {"eligible-for-climate-smart-input-voucher": False},
    ),
    ScenarioCase(
        "livestock movement permit eligible",
        "farmer_voucher",
        "movement-permit",
        200,
        {"eligible-for-livestock-movement-permit": True},
    ),
    ScenarioCase("livestock purpose denial", "farmer_voucher", "purpose-denial", range(400, 500), {}),
    ScenarioCase(
        "citizen self-service summary",
        "citizen",
        "positive",
        200,
        {
            "population-record-active": True,
            "civil-record-linked": True,
            "citizen-self-service-summary": True,
        },
    ),
    ScenarioCase("citizen unsupported purpose denial", "citizen", "purpose-denial", range(400, 500), {}),
)


def main() -> int:
    load_dotenv(ROOT / ".env")
    failures: list[str] = []

    for service in SERVICES:
        failures.extend(check_service(service))

    for case in SCENARIO_CASES:
        failures.extend(check_case(case))

    if failures:
        for failure in failures:
            print(f"smoke-live: {failure}", file=sys.stderr)
        return 1

    print(f"smoke-live: {len(SERVICES)} services and {len(SCENARIO_CASES)} scenario checks passed")
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
        if raw_value == "":
            os.environ[key] = ""
            continue
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


def check_service(service: NotaryService) -> list[str]:
    failures: list[str] = []
    base_url = os.environ.get(service.url_env, service.default_url)
    if not os.environ.get(service.token_env):
        return [f"{service.name}: missing {service.token_env}; run `just generate` before live smoke"]

    health = wait_for_health(base_url, service.name)
    if health is not None:
        failures.append(health)

    headers = auth_headers(os.environ[service.token_env], service.purpose, "application/json")
    result = http_json("GET", joined_url(base_url, "/v1/claims"), headers, timeout=5.0)
    if result.status != 200:
        failures.append(f"{service.name}: GET /v1/claims returned {result.status}; body={compact_body(result.body)}")
        return failures

    ids = catalog_claim_ids(result.body)
    missing = sorted(set(service.claim_ids) - ids)
    if missing:
        failures.append(f"{service.name}: missing claims from catalogue: {', '.join(missing)}")
    return failures


def wait_for_health(base_url: str, name: str) -> str | None:
    url = joined_url(base_url, "/healthz")
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
    return f"{name}: /healthz did not become ready at {url} ({detail})"


def check_case(case: ScenarioCase) -> list[str]:
    module = importlib.import_module(f"scenarios.{case.module_name}")
    result = module.run_step({}, case.step_id)
    response = result.get("response_source", {})
    status = response.get("status")
    if not status_matches(status, case.expected_status):
        return [f"{case.name}: expected HTTP {format_expected(case.expected_status)}, got {status}; body={compact_body(response.get('body'))}"]

    if not case.expected_values:
        return []

    values = claim_values(response.get("body", {}))
    failures = []
    for claim_id, expected in case.expected_values.items():
        actual = values.get(claim_id)
        if actual is not expected:
            failures.append(f"{case.name}: expected {claim_id}={expected}, got {actual}; body={compact_body(response.get('body'))}")
    return failures


def status_matches(status: Any, expected: int | tuple[int, ...] | range) -> bool:
    if not isinstance(status, int):
        return False
    if isinstance(expected, int):
        return status == expected
    return status in expected


def format_expected(expected: int | tuple[int, ...] | range) -> str:
    if isinstance(expected, range):
        return f"{expected.start}-{expected.stop - 1}"
    if isinstance(expected, tuple):
        return ",".join(str(item) for item in expected)
    return str(expected)


def catalog_claim_ids(body: Any) -> set[str]:
    if not isinstance(body, dict):
        return set()
    claims = body.get("data", [])
    if not isinstance(claims, list):
        return set()
    return {claim.get("id") for claim in claims if isinstance(claim, dict) and isinstance(claim.get("id"), str)}


def claim_values(body: Any) -> dict[str, bool | None]:
    if not isinstance(body, dict):
        return {}
    results = body.get("results", [])
    if not isinstance(results, list):
        return {}
    values: dict[str, bool | None] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        claim_id = item.get("claim_id")
        if not isinstance(claim_id, str):
            continue
        value = item.get("value")
        values[claim_id] = value if isinstance(value, bool) else item.get("satisfied")
    return values


def compact_body(body: Any) -> str:
    text = str(body)
    return text if len(text) <= 500 else text[:497] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
