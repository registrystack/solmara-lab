#!/usr/bin/env python3
"""Application-level child-benefit Evidence collector.

The collector owns no eligibility rule. It asks one Evidence deployment for
four separately governed requirements and returns their signed concept values
with source attribution. Registry rows remain behind each authority's Relay.
"""

from __future__ import annotations

import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from scenarios.common import PURPOSES, evidence_body, evidence_headers, http_json, normalized_evidence_result
from scenarios.service_config import requirement_id, service_token, service_url


API_VERSION = "solmara-child-benefit-evidence/v2"
FEDERATOR_SERVICE_ID = "child-benefit-federator"
FEDERATOR_TOKEN_ENV = "CHILD_BENEFIT_FEDERATOR_TOKEN"
CHILD_PURPOSE = PURPOSES["child_benefit"]
MAX_REQUEST_BODY_BYTES = 64 * 1024
SOURCE_ROUTES: tuple[dict[str, Any], ...] = (
    {"client_id": "cra-child-benefit", "authority": "Civil Registration Authority", "claims": ("birth-is-registered", "child-age-under-5")},
    {"client_id": "nia-child-benefit", "authority": "National Identity Agency", "claims": ("population-record-active",)},
    {"client_id": "sro-child-benefit", "authority": "Social Registry Office", "claims": ("household-below-poverty-threshold",)},
    {"client_id": "programme-child-benefit", "authority": "MoSD Programme MIS", "claims": ("not-already-enrolled",)},
)
CLAIM_ROUTES = {claim: route for route in SOURCE_ROUTES for claim in route["claims"]}


class ChildBenefitFederatorHandler(BaseHTTPRequestHandler):
    server_version = "SolmaraChildBenefitEvidence/2.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/healthz"}:
            self.write_json({"status": "ok", "service": FEDERATOR_SERVICE_ID})
            return
        if path == "/v1/claims":
            if not self.require_token():
                return
            self.write_json({"schema_version": API_VERSION, "claims": [{"claim_id": claim, "authority": route["authority"]} for claim, route in CLAIM_ROUTES.items()]})
            return
        self.write_problem(HTTPStatus.NOT_FOUND, "not_found", "No such application route.")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/v1/evaluations":
            self.write_problem(HTTPStatus.NOT_FOUND, "not_found", "No such application route.")
            return
        if not self.require_token():
            return
        purpose = self.headers.get("Data-Purpose", "")
        if purpose != CHILD_PURPOSE:
            self.write_problem(HTTPStatus.FORBIDDEN, "not_authorized", "Only child-benefit-review is permitted.")
            return
        body = self.read_body()
        if body is None:
            return
        subject = subject_id(body)
        claims = requested_claims(body)
        if not subject or not claims or len(claims) != len(set(claims)) or any(claim not in CLAIM_ROUTES for claim in claims):
            self.write_problem(HTTPStatus.BAD_REQUEST, "invalid_request", "Name one UIN and unique supported claims.")
            return
        token = service_token("cra-child-benefit")
        if not token:
            self.write_problem(HTTPStatus.SERVICE_UNAVAILABLE, "mint_unavailable", "No Evidence access token is available.")
            return
        results: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        signed_evidence: list[Any] = []
        for route in SOURCE_ROUTES:
            requested = [claim for claim in claims if claim in route["claims"]]
            if not requested:
                continue
            url = service_url(route["client_id"])
            headers = evidence_headers(token)
            request = evidence_body(subject, requirement_id(route["client_id"]), purpose)
            response = normalized_evidence_result(http_json("POST", url, headers, request))
            if response.status is None or not 200 <= response.status < 300:
                self.write_problem(HTTPStatus.BAD_GATEWAY, "evidence_unavailable", f"{route['authority']} evidence was unavailable.")
                return
            returned = {item["claim_id"]: item for item in response.body.get("results", [])}
            if any(claim not in returned for claim in requested):
                self.write_problem(HTTPStatus.BAD_GATEWAY, "evidence_incomplete", f"{route['authority']} omitted a requested concept.")
                return
            results.extend({**returned[claim], "authority": route["authority"]} for claim in requested)
            signed_evidence.append(response.body.get("signed_evidence"))
            trace.append({"authority": route["authority"], "service_id": "registry-evidence", "requirement": requirement_id(route["client_id"]), "status": response.status})
        self.write_json({"schema_version": API_VERSION, "orchestration": {"service_id": FEDERATOR_SERVICE_ID, "decision": "not_composed"}, "purpose": purpose, "target": {"type": "Person", "binding": "withheld"}, "results": results, "signed_evidence": signed_evidence, "source_trace": trace})

    def require_token(self) -> bool:
        expected = os.environ.get(FEDERATOR_TOKEN_ENV, "")
        received = self.headers.get("x-api-key", "")
        if expected and hmac.compare_digest(received, expected):
            return True
        self.write_problem(HTTPStatus.UNAUTHORIZED, "authentication_required", "A valid local application token is required.")
        return False

    def read_body(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BODY_BYTES:
            self.write_problem(HTTPStatus.BAD_REQUEST, "invalid_request", "A bounded JSON object is required.")
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            value = None
        if not isinstance(value, dict):
            self.write_problem(HTTPStatus.BAD_REQUEST, "invalid_request", "A JSON object is required.")
            return None
        return value

    def write_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        content_type: str = "application/json",
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_problem(self, status: HTTPStatus, code: str, detail: str) -> None:
        self.write_json(
            {
                "type": f"https://id.registrystack.org/problems/solmara/{code}",
                "title": code.replace("_", " ").title(),
                "status": int(status),
                "code": code,
                "detail": detail,
            },
            status,
            content_type="application/problem+json",
        )

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("CHILD_BENEFIT_FEDERATOR_ACCESS_LOG") == "1":
            super().log_message(format, *args)


def subject_id(body: dict[str, Any]) -> str:
    target = body.get("target")
    identifiers = target.get("identifiers") if isinstance(target, dict) else None
    if not isinstance(identifiers, list):
        return ""
    for identifier in identifiers:
        if isinstance(identifier, dict) and identifier.get("scheme") == "solmara_uin" and isinstance(identifier.get("value"), str):
            return identifier["value"]
    return ""


def requested_claims(body: dict[str, Any]) -> list[str]:
    claims = body.get("claims")
    return [claim for claim in claims if isinstance(claim, str)] if isinstance(claims, list) else []


def main() -> int:
    host = os.environ.get("CHILD_BENEFIT_FEDERATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CHILD_BENEFIT_FEDERATOR_PORT", "8080"))
    ThreadingHTTPServer((host, port), ChildBenefitFederatorHandler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
