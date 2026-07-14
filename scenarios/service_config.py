#!/usr/bin/env python3
"""Runtime endpoint lookup for guided Solmara scenarios."""

from __future__ import annotations

import os
from urllib.parse import urljoin


SERVICE_ENDPOINTS = {
    "child-benefit-federator": {
        "url_env": "CHILD_BENEFIT_FEDERATOR_URL",
        "token_env": "CHILD_BENEFIT_FEDERATOR_TOKEN",
        "default_url": "http://127.0.0.1:4321",
    },
    "cra-child-benefit": {
        "service_id": "cra-notary",
        "url_env": "CRA_NOTARY_URL",
        "token_env": "CRA_CHILD_BENEFIT_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4325",
    },
    "nia-child-benefit": {
        "service_id": "nia-notary",
        "url_env": "NIA_NOTARY_URL",
        "token_env": "NIA_CHILD_BENEFIT_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4326",
    },
    "sro-child-benefit": {
        "service_id": "sro-notary",
        "url_env": "SRO_NOTARY_URL",
        "token_env": "SRO_CHILD_BENEFIT_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4327",
    },
    "programme-child-benefit": {
        "service_id": "programme-notary",
        "url_env": "PROGRAMME_NOTARY_URL",
        "token_env": "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4328",
    },
    "cra-pension": {
        "service_id": "cra-notary",
        "url_env": "CRA_NOTARY_URL",
        "token_env": "CRA_PENSION_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4325",
    },
    "sipf-pension": {
        "service_id": "sipf-notary",
        "url_env": "SIPF_NOTARY_URL",
        "token_env": "SIPF_PENSION_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4322",
    },
    "cra-citizen": {
        "service_id": "cra-notary",
        "url_env": "CRA_NOTARY_URL",
        "token_env": "CRA_CITIZEN_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4325",
    },
    "nia-citizen": {
        "service_id": "nia-notary",
        "url_env": "NIA_NOTARY_URL",
        "token_env": "NIA_CITIZEN_CLIENT_TOKEN",
        "default_url": "http://127.0.0.1:4326",
    },
    "nagdi-notary": {
        "service_id": "nagdi-notary",
        "url_env": "NAGDI_NOTARY_URL",
        "token_env": "NAGDI_NOTARY_TOKEN",
        "default_url": "http://127.0.0.1:4323",
    },
}


def service_url(service_id: str, path: str) -> str:
    entry = service_entry(service_id)
    base_url = os.environ.get(entry["url_env"], entry["default_url"])
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def service_token(service_id: str) -> str:
    return os.environ.get(service_token_env(service_id), "")


def service_token_env(service_id: str) -> str:
    return service_entry(service_id)["token_env"]


def authority_service_id(service_id: str) -> str:
    entry = service_entry(service_id)
    return entry.get("service_id", service_id)


def service_entry(service_id: str) -> dict[str, str]:
    try:
        return SERVICE_ENDPOINTS[service_id]
    except KeyError as error:
        raise ValueError(f"unknown service endpoint: {service_id}") from error
