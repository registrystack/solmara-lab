#!/usr/bin/env python3
"""Authority-owned Registry Evidence endpoints and requirement identifiers."""

from __future__ import annotations

import os
from typing import Any

from .common import evidence_access_token, joined_url


BASE = "https://id.registrystack.org/solmara/requirement"
PROVIDER_BASE = "https://id.registrystack.org/solmara/evidence"
EVIDENCE_TYPE_BASE = "https://id.registrystack.org/solmara/evidence-type"
AUTHORITY_DID_BASE = "did:web:id.registrystack.org:solmara:authority"
AUTHORITY_DIRECTORY: dict[str, dict[str, str]] = {
    "cra": {
        "name": "Civil Registration Authority",
        "base_url": "https://cra-evidence.solmara.registrystack.org",
        "env": "SOLMARA_CRA_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:cra",
        "provider": f"{PROVIDER_BASE}/cra",
    },
    "nia": {
        "name": "National Identity Agency",
        "base_url": "https://nia-evidence.solmara.registrystack.org",
        "env": "SOLMARA_NIA_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:nia",
        "provider": f"{PROVIDER_BASE}/nia",
    },
    "sro": {
        "name": "Social Registry Office",
        "base_url": "https://sro-evidence.solmara.registrystack.org",
        "env": "SOLMARA_SRO_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:sro",
        "provider": f"{PROVIDER_BASE}/sro",
    },
    "mosd-programme": {
        "name": "Ministry of Social Development Programme MIS",
        "base_url": "https://mosd-programme-evidence.solmara.registrystack.org",
        "env": "SOLMARA_MOSD_PROGRAMME_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:mosd-programme-mis",
        "provider": f"{PROVIDER_BASE}/mosd-programme",
    },
    "sipf": {
        "name": "Social Insurance and Pensions Fund",
        "base_url": "https://sipf-evidence.solmara.registrystack.org",
        "env": "SOLMARA_SIPF_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:sipf",
        "provider": f"{PROVIDER_BASE}/sipf",
    },
    "nagdi": {
        "name": "National Agricultural Data Institute",
        "base_url": "https://nagdi-evidence.solmara.registrystack.org",
        "env": "SOLMARA_NAGDI_EVIDENCE_URL",
        "issuer": f"{AUTHORITY_DID_BASE}:nagdi",
        "provider": f"{PROVIDER_BASE}/nagdi",
    },
}

REQUIREMENT_DIRECTORY: dict[str, dict[str, Any]] = {
    "cra-child-benefit": {"authority": "cra", "requirement": f"{BASE}/cra-child-benefit/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/cra-child-benefit/v1", "source": "immutable extract", "maximum_validity_seconds": 3600, "concepts": ("birth-is-registered", "child-age-under-5")},
    "nia-child-benefit": {"authority": "nia", "requirement": f"{BASE}/nia-child-benefit/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/population-active/v1", "source": "immutable extract", "maximum_validity_seconds": 3600, "concepts": ("population-record-active",)},
    "sro-child-benefit": {"authority": "sro", "requirement": f"{BASE}/sro-child-benefit/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/poverty-priority/v1", "source": "immutable extract", "maximum_validity_seconds": 3600, "concepts": ("household-below-poverty-threshold",)},
    "programme-child-benefit": {"authority": "mosd-programme", "requirement": f"{BASE}/mosd-child-benefit/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/not-enrolled/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("not-already-enrolled",)},
    "cra-pension": {"authority": "cra", "requirement": f"{BASE}/cra-pension-death/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/cra-death-status/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("person-is-deceased",)},
    "sipf-pension": {"authority": "sipf", "requirement": f"{BASE}/sipf-pension-payment/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/pension-payment-active/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("pension-payment-active",)},
    "sipf-survivor": {"authority": "sipf", "requirement": f"{BASE}/sipf-survivor-benefit/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/survivor-benefit/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("survivor-is-eligible",)},
    "cra-citizen": {"authority": "cra", "requirement": f"{BASE}/cra-citizen-record/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/civil-record-linked/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("civil-record-linked",)},
    "nia-citizen": {"authority": "nia", "requirement": f"{BASE}/nia-citizen-status/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/citizen-population-active/v1", "source": "immutable extract", "maximum_validity_seconds": 3600, "concepts": ("citizen-population-record-active",)},
    "nagdi-voucher": {"authority": "nagdi", "requirement": f"{BASE}/nagdi-voucher/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/climate-smart-voucher/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("farmer-registered", "data-use-authorized-for-purpose", "eligible-for-climate-smart-input-voucher")},
    "nagdi-livestock": {"authority": "nagdi", "requirement": f"{BASE}/nagdi-livestock/v1", "evidence_type": f"{EVIDENCE_TYPE_BASE}/livestock-movement/v1", "source": "Relay lookup", "maximum_validity_seconds": 300, "concepts": ("registered-herd", "origin-district-not-quarantined-for-species", "eligible-for-livestock-movement-permit")},
}
REQUIREMENTS = {key: value["requirement"] for key, value in REQUIREMENT_DIRECTORY.items()}
_REQUIREMENT_ALIASES = {value: key for key, value in REQUIREMENTS.items()}


def requirement_config(service_id: str) -> dict[str, Any]:
    try:
        requirement = REQUIREMENT_DIRECTORY[service_id]
        authority = AUTHORITY_DIRECTORY[requirement["authority"]]
    except KeyError as error:
        raise ValueError(f"unknown Evidence requirement: {service_id}") from error
    return {**requirement, **authority, "service_id": service_id}


def config_for_requirement(requirement: str) -> dict[str, Any]:
    try:
        return requirement_config(_REQUIREMENT_ALIASES[requirement])
    except KeyError as error:
        raise ValueError("unknown Evidence requirement") from error


def service_url(service_id: str, path: str = "/v1/evidence") -> str:
    if service_id == "child-benefit-federator":
        return joined_url(
            os.environ.get("CHILD_BENEFIT_FEDERATOR_URL", "http://127.0.0.1:4321"),
            path,
        )
    config = requirement_config(service_id)
    return joined_url(os.environ.get(config["env"], config["base_url"]), path)


def service_token(service_id: str) -> str:
    if service_id == "child-benefit-federator":
        return os.environ.get("CHILD_BENEFIT_FEDERATOR_TOKEN", "")
    requirement_config(service_id)
    return evidence_access_token()


def service_token_env(service_id: str) -> str:
    return (
        "CHILD_BENEFIT_FEDERATOR_TOKEN"
        if service_id == "child-benefit-federator"
        else "SOLMARA_EVIDENCE_CLIENT_KEY"
    )


def requirement_id(service_id: str) -> str:
    return str(requirement_config(service_id)["requirement"])


def authority_service_id(service_id: str) -> str:
    return f"{requirement_config(service_id)['authority']}-evidence"
