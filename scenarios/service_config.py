#!/usr/bin/env python3
"""One Evidence endpoint with requirement-specific policy identifiers."""

from __future__ import annotations

import os

from .common import evidence_access_token, joined_url


BASE = "https://id.registrystack.org/solmara/requirement"
REQUIREMENTS = {
    "cra-child-benefit": f"{BASE}/cra-child-benefit/v1",
    "nia-child-benefit": f"{BASE}/nia-child-benefit/v1",
    "sro-child-benefit": f"{BASE}/sro-child-benefit/v1",
    "programme-child-benefit": f"{BASE}/mosd-child-benefit/v1",
    "cra-pension": f"{BASE}/cra-pension-death/v1",
    "sipf-pension": f"{BASE}/sipf-pension-payment/v1",
    "sipf-survivor": f"{BASE}/sipf-survivor-benefit/v1",
    "cra-citizen": f"{BASE}/cra-citizen-record/v1",
    "nia-citizen": f"{BASE}/nia-citizen-status/v1",
    "nagdi-voucher": f"{BASE}/nagdi-voucher/v1",
    "nagdi-livestock": f"{BASE}/nagdi-livestock/v1",
}


def service_url(service_id: str, path: str = "/v1/evidence") -> str:
    if service_id == "child-benefit-federator":
        return joined_url(
            os.environ.get("CHILD_BENEFIT_FEDERATOR_URL", "http://127.0.0.1:4321"),
            path,
        )
    return joined_url(
        os.environ.get("SOLMARA_EVIDENCE_URL", "https://evidence.solmara.invalid"),
        path,
    )


def service_token(service_id: str) -> str:
    if service_id == "child-benefit-federator":
        return os.environ.get("CHILD_BENEFIT_FEDERATOR_TOKEN", "")
    return evidence_access_token()


def service_token_env(service_id: str) -> str:
    return (
        "CHILD_BENEFIT_FEDERATOR_TOKEN"
        if service_id == "child-benefit-federator"
        else "SOLMARA_EVIDENCE_CLIENT_KEY"
    )


def requirement_id(service_id: str) -> str:
    try:
        return REQUIREMENTS[service_id]
    except KeyError as error:
        raise ValueError(f"unknown Evidence requirement: {service_id}") from error


def authority_service_id(service_id: str) -> str:
    return "registry-evidence"
