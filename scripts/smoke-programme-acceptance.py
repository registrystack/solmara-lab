#!/usr/bin/env python3
"""Run sanitized programme acceptance against the live Scenario Runner HTTP API."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable


RUNNER_URL = os.environ.get("SOLMARA_SCENARIO_RUNNER_URL", "http://127.0.0.1:8080")
FEDERATOR_URL = os.environ.get(
    "SOLMARA_CHILD_BENEFIT_FEDERATOR_URL",
    os.environ.get("CHILD_BENEFIT_FEDERATOR_URL", "http://child-benefit-federator:8080"),
)
READY_TIMEOUT_SECONDS = float(os.environ.get("SOLMARA_SMOKE_READY_TIMEOUT_SECONDS", "90"))

CRA = "did:web:id.registrystack.org:solmara:authority:cra"
NIA = "did:web:id.registrystack.org:solmara:authority:nia"
SRO = "did:web:id.registrystack.org:solmara:authority:sro"
MOSD = "did:web:id.registrystack.org:solmara:authority:mosd-programme-mis"
SIPF = "did:web:id.registrystack.org:solmara:authority:sipf"
NAGDI = "did:web:id.registrystack.org:solmara:authority:nagdi"

CHILD_CLAIMS = {
    "birth-is-registered": CRA,
    "child-age-under-5": CRA,
    "population-record-active": NIA,
    "household-below-poverty-threshold": SRO,
    "not-already-enrolled": MOSD,
}
PENSION_CLAIMS = {
    "person-is-deceased": CRA,
    "pension-payment-active": SIPF,
}
SURVIVOR_CLAIMS = {"survivor-is-eligible": SIPF}
VOUCHER_CLAIMS = {
    "farmer-registered": NAGDI,
    "data-use-authorized-for-purpose": NAGDI,
    "eligible-for-climate-smart-input-voucher": NAGDI,
}
LIVESTOCK_CLAIMS = {
    "registered-herd": NAGDI,
    "origin-district-not-quarantined-for-species": NAGDI,
    "eligible-for-livestock-movement-permit": NAGDI,
}


@dataclass(frozen=True)
class HttpResult:
    status: int | None
    body: Any


@dataclass(frozen=True)
class Check:
    label: str
    run: Callable[[], bool]


def joined_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def request_json(method: str, url: str, body: Any | None = None, timeout: float = 30.0) -> HttpResult:
    data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, parse_json(response.read()))
    except urllib.error.HTTPError as error:
        try:
            return HttpResult(error.code, parse_json(error.read()))
        finally:
            error.close()
    except Exception:
        return HttpResult(None, {})


def parse_json(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=closed_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}


def closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def wait_for_runner() -> bool:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = request_json("GET", joined_url(RUNNER_URL, "/health"), timeout=2.0)
        if result.status == 200 and result.body == {"service": "scenario-runner", "status": "ok"}:
            return True
        time.sleep(1)
    return False


def run_scenario(scenario: str, step: str) -> dict[str, Any] | None:
    result = request_json(
        "POST",
        joined_url(RUNNER_URL, f"/v1/scenarios/{scenario}/steps/{step}/run"),
        {},
    )
    if result.status != 200 or not isinstance(result.body, dict):
        return None
    if result.body.get("scenario_id") != scenario:
        return None
    payload = result.body.get("result")
    return payload if isinstance(payload, dict) else None


def verified_claims(
    payload: dict[str, Any] | None,
    expected_claims: dict[str, str],
    expected_services: dict[str, tuple[str, str]],
) -> bool:
    if payload is None or payload.get("response_source") != {"status": 200, "code": "ok"}:
        return False
    results = payload.get("results")
    traces = payload.get("source_trace")
    presentations = payload.get("presentations")
    if not isinstance(results, list) or not isinstance(traces, list) or not isinstance(presentations, list):
        return False
    if len(results) != len(expected_claims) or len(traces) != len(expected_services):
        return False

    actual_claims: dict[str, str] = {}
    expected_identity_by_issuer = {
        issuer: source for issuer, source in expected_services.values()
    }
    for item in results:
        if not isinstance(item, dict) or item.get("satisfied") is not True or item.get("value") is not True:
            return False
        claim = item.get("claim_id")
        presentation = item.get("presentation")
        if not isinstance(claim, str) or not isinstance(presentation, dict):
            return False
        issuer = presentation.get("issuer")
        if (
            set(presentation) != {"authority", "issuer", "provider", "source"}
            or not all(isinstance(presentation.get(key), str) for key in presentation)
            or not isinstance(issuer, str)
            or presentation.get("source") != expected_identity_by_issuer.get(issuer)
            or claim in actual_claims
        ):
            return False
        actual_claims[claim] = issuer
    if actual_claims != expected_claims:
        return False

    actual_presentation_issuers: list[str] = []
    for presentation in presentations:
        if (
            not isinstance(presentation, dict)
            or set(presentation) != {"authority", "issuer", "provider", "source"}
            or not all(isinstance(presentation.get(key), str) for key in presentation)
            or presentation.get("source")
            != expected_identity_by_issuer.get(presentation.get("issuer"))
        ):
            return False
        actual_presentation_issuers.append(presentation["issuer"])
    if Counter(actual_presentation_issuers) != Counter(
        issuer for issuer, _ in expected_services.values()
    ):
        return False

    actual_services: set[str] = set()
    trace_issuers: set[str] = set()
    for trace in traces:
        if (
            not isinstance(trace, dict)
            or set(trace)
            != {"authority", "service_id", "issuer", "provider", "source", "status"}
            or not all(
                isinstance(trace.get(key), str)
                for key in ("authority", "service_id", "issuer", "provider", "source")
            )
            or trace.get("status") != 200
        ):
            return False
        service = trace.get("service_id")
        if not isinstance(service, str) or service not in expected_services or service in actual_services:
            return False
        expected_identity = expected_services.get(service)
        if expected_identity is None or (trace.get("issuer"), trace.get("source")) != expected_identity:
            return False
        actual_services.add(service)
        trace_issuers.add(expected_identity[0])
    return actual_services == set(expected_services) and trace_issuers == set(expected_claims.values())


def child_benefit_positive() -> bool:
    return verified_claims(
        run_scenario("birth-to-child-benefit", "positive"),
        CHILD_CLAIMS,
        {
            "cra-evidence": (CRA, "immutable extract"),
            "nia-evidence": (NIA, "immutable extract"),
            "sro-evidence": (SRO, "immutable extract"),
            "mosd-programme-evidence": (MOSD, "Relay lookup"),
        },
    )


def pension_stop() -> bool:
    payload = run_scenario("death-to-pension-survivor", "stop-payment")
    return bool(
        verified_claims(
            payload,
            PENSION_CLAIMS,
            {
                "cra-evidence": (CRA, "Relay lookup"),
                "sipf-evidence": (SIPF, "Relay lookup"),
            },
        )
        and payload is not None
        and payload.get("derived_decisions")
        == {"pension-payment-should-stop": True, "owner": "pension-review-application"}
        and excludes_cause_of_death(payload)
    )


def pension_survivor() -> bool:
    payload = run_scenario("death-to-pension-survivor", "survivor-benefit")
    return verified_claims(
        payload,
        SURVIVOR_CLAIMS,
        {"sipf-evidence": (SIPF, "Relay lookup")},
    ) and excludes_cause_of_death(payload)


def agriculture_voucher() -> bool:
    return verified_claims(
        run_scenario("farmer-climate-smart-voucher", "positive"),
        VOUCHER_CLAIMS,
        {"nagdi-evidence": (NAGDI, "Relay lookup")},
    )


def agriculture_livestock() -> bool:
    return verified_claims(
        run_scenario("farmer-climate-smart-voucher", "movement-permit"),
        LIVESTOCK_CLAIMS,
        {"nagdi-evidence": (NAGDI, "Relay lookup")},
    )


def excludes_cause_of_death(payload: Any) -> bool:
    serialized = json.dumps(payload, sort_keys=True).lower()
    return not any(
        marker in serialized
        for marker in ("cause-of-death", "cause_of_death", "causeofdeath", "cause of death")
    )


def generic_scenario_refusal(scenario: str, step: str) -> bool:
    payload = run_scenario(scenario, step)
    if payload is None:
        return False
    response = payload.get("response_source")
    return bool(
        isinstance(response, dict)
        and set(response) == {"status", "code"}
        and isinstance(response.get("status"), int)
        and 400 <= response["status"] < 500
        and response.get("code") == "request_refused"
        and payload.get("results") == []
        and payload.get("presentations") == []
    )


def application_unauthorized() -> bool:
    result = request_json("GET", joined_url(FEDERATOR_URL, "/v1/claims"), timeout=8.0)
    body = result.body
    return bool(
        result.status == 401
        and isinstance(body, dict)
        and set(body) == {"type", "title", "status", "code", "detail"}
        and body.get("status") == 401
        and body.get("code") == "authentication_required"
        and body.get("type")
        == "https://id.registrystack.org/problems/solmara/authentication_required"
    )


def checks() -> tuple[Check, ...]:
    return (
        Check("runner-ready", wait_for_runner),
        Check("child-benefit-four-authorities-five-concepts", child_benefit_positive),
        Check("pension-cra-sipf-stop-decision", pension_stop),
        Check("pension-survivor-minimized-assertion", pension_survivor),
        Check("agriculture-voucher", agriculture_voucher),
        Check("agriculture-livestock", agriculture_livestock),
        Check(
            "child-benefit-wrong-purpose-generic-refusal",
            lambda: generic_scenario_refusal("birth-to-child-benefit", "purpose-denial"),
        ),
        Check(
            "pension-unauthorized-requirement-generic-refusal",
            lambda: generic_scenario_refusal("death-to-pension-survivor", "cause-of-death-denial"),
        ),
        Check(
            "agriculture-wrong-purpose-generic-refusal",
            lambda: generic_scenario_refusal("farmer-climate-smart-voucher", "purpose-denial"),
        ),
        Check("programme-application-unauthorized-generic-refusal", application_unauthorized),
    )


def main() -> int:
    failed = False
    for check in checks():
        try:
            passed = check.run()
        except Exception:
            passed = False
        print(f"programme-acceptance: {'PASS' if passed else 'FAIL'} {check.label}")
        failed = failed or not passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
