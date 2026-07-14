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
    "pension-notary": {
        "url_env": "PENSION_NOTARY_URL",
        "token_env": "PENSION_NOTARY_TOKEN",
        "default_url": "http://127.0.0.1:4322",
    },
    "nagdi-notary": {
        "url_env": "NAGDI_NOTARY_URL",
        "token_env": "NAGDI_NOTARY_TOKEN",
        "default_url": "http://127.0.0.1:4323",
    },
    "citizen-notary": {
        "url_env": "PORTAL_CITIZEN_NOTARY_URL",
        "token_env": "PORTAL_CITIZEN_NOTARY_TOKEN",
        "default_url": "http://127.0.0.1:4324",
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


def service_entry(service_id: str) -> dict[str, str]:
    try:
        return SERVICE_ENDPOINTS[service_id]
    except KeyError as error:
        raise ValueError(f"unknown service endpoint: {service_id}") from error
