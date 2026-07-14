#!/usr/bin/env python3
"""Child-benefit evidence collector for the Solmara lab.

This is an application service, not a Notary and not an eligibility engine.
It asks the four authority-owned Notaries for their minimized predicates over
the ordinary Registry Notary HTTP API, then returns a source-attributed
evidence set. The programme policy layer remains responsible for eligibility.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from scenarios.common import (
    CLAIM_RESULT_FORMAT,
    PURPOSES,
    StepHttpResult,
    auth_headers,
    evaluation_body,
    http_json,
)
from scenarios.service_config import (
    authority_service_id,
    service_token,
    service_token_env,
    service_url,
)


API_VERSION = "solmara-child-benefit-evidence/v1"
FEDERATOR_SERVICE_ID = "child-benefit-federator"
FEDERATOR_TOKEN_ENV = "CHILD_BENEFIT_FEDERATOR_TOKEN"
CHILD_PURPOSE = PURPOSES["child_benefit"]
SUPPORTED_DISCLOSURES = {"predicate"}
SENSITIVE_RAW_CLAIMS = {"household-poverty-score", "household-profile"}
MAX_REQUEST_BODY_BYTES = 64 * 1024
ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


SOURCE_ROUTES: tuple[dict[str, Any], ...] = (
    {
        "client_id": "cra-child-benefit",
        "authority": "Civil Registration Authority",
        "claims": ("birth-is-registered", "child-age-under-5"),
    },
    {
        "client_id": "nia-child-benefit",
        "authority": "National Identity Agency",
        "claims": ("population-record-active",),
    },
    {
        "client_id": "sro-child-benefit",
        "authority": "Social Registry Office",
        "claims": ("household-below-poverty-threshold",),
    },
    {
        "client_id": "programme-child-benefit",
        "authority": "MoSD Programme MIS",
        "claims": ("not-already-enrolled",),
    },
)
CLAIM_ROUTES = {
    claim_id: route for route in SOURCE_ROUTES for claim_id in route["claims"]
}


class RequestBodyError(Exception):
    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class AuthorityUpstreamError(Exception):
    def __init__(self, route: dict[str, Any], status: int | None, code: str) -> None:
        super().__init__(code)
        self.route = route
        self.status = status
        self.code = code


class ChildBenefitFederatorHandler(BaseHTTPRequestHandler):
    server_version = "SolmaraChildBenefitEvidence/1.0"

    def do_GET(self) -> None:
        parts = path_parts(self.path)
        if parts in (["health"], ["healthz"]):
            self.write_json({"status": "ok", "service": FEDERATOR_SERVICE_ID})
            return
        if parts == ["v1", "claims"]:
            if not self.require_token():
                return
            purpose = self.headers.get("Data-Purpose", "")
            if purpose and purpose != CHILD_PURPOSE:
                self.write_problem(
                    HTTPStatus.FORBIDDEN,
                    "pdp.purpose_not_permitted",
                    "Purpose not permitted",
                    "This service only collects evidence for child-benefit review.",
                )
                return
            self.write_json(claim_catalog())
            return
        self.write_problem(
            HTTPStatus.NOT_FOUND, "not_found", "Not found", "No such application route."
        )

    def do_POST(self) -> None:
        if path_parts(self.path) != ["v1", "evaluations"]:
            self.write_problem(
                HTTPStatus.NOT_FOUND,
                "not_found",
                "Not found",
                "No such application route.",
            )
            return
        if not self.require_token():
            return
        purpose = self.headers.get("Data-Purpose", "")
        if purpose != CHILD_PURPOSE:
            self.write_problem(
                HTTPStatus.FORBIDDEN,
                "pdp.purpose_not_permitted",
                "Purpose not permitted",
                "This service only collects evidence for child-benefit review.",
            )
            return

        try:
            body = self.read_body()
        except RequestBodyError as error:
            self.write_problem(
                error.status,
                "request.invalid",
                "Invalid evidence request",
                error.detail,
            )
            return

        if body.get("disclosure", "predicate") not in SUPPORTED_DISCLOSURES:
            self.write_problem(
                HTTPStatus.FORBIDDEN,
                "pdp.purpose_not_permitted",
                "Disclosure not permitted",
                "This purpose permits minimized predicates only.",
            )
            return
        requested = requested_claims(body)
        if any(claim in SENSITIVE_RAW_CLAIMS for claim in requested):
            self.write_problem(
                HTTPStatus.FORBIDDEN,
                "pdp.purpose_not_permitted",
                "Disclosure not permitted",
                "Raw source fields are not available through this purpose.",
            )
            return
        if body.get("format", "application/json") != "application/json":
            self.write_problem(
                HTTPStatus.BAD_REQUEST,
                "request.unsupported_format",
                "Unsupported response format",
                "Omit format or set it to application/json.",
            )
            return
        if not accepts_media_type(self.headers.get("Accept", ""), "application/json"):
            self.write_problem(
                HTTPStatus.NOT_ACCEPTABLE,
                "request.not_acceptable",
                "Unsupported response representation",
                "Set Accept to application/json.",
            )
            return

        subject = subject_id(body)
        unknown = [claim for claim in requested if claim not in CLAIM_ROUTES]
        if (
            not subject
            or not requested
            or unknown
            or len(requested) != len(set(requested))
        ):
            self.write_problem(
                HTTPStatus.BAD_REQUEST,
                "request.invalid",
                "Invalid evidence request",
                "The request must name unique supported child-benefit predicates and a solmara_uin target.",
            )
            return

        try:
            evidence = collect_evidence(subject, requested, purpose, body.get("target"))
        except AuthorityUpstreamError as error:
            self.write_problem(
                HTTPStatus.BAD_GATEWAY,
                "authority.upstream_failed",
                "Authority evidence unavailable",
                f"{error.route['authority']} did not return the requested minimized evidence.",
            )
            return
        self.write_json(evidence)

    def require_token(self) -> bool:
        expected = os.environ.get(FEDERATOR_TOKEN_ENV, "")
        received = self.headers.get("x-api-key", "")
        if expected and hmac.compare_digest(received, expected):
            return True
        self.write_problem(
            HTTPStatus.UNAUTHORIZED,
            "auth.missing_or_invalid",
            "Authentication required",
            f"Set the {FEDERATOR_TOKEN_ENV} synthetic lab token.",
        )
        return False

    def read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else 0
        except ValueError as error:
            raise RequestBodyError(
                HTTPStatus.BAD_REQUEST, "Content-Length must be a decimal byte count."
            ) from error
        if length <= 0:
            raise RequestBodyError(
                HTTPStatus.BAD_REQUEST, "A non-empty JSON request body is required."
            )
        if length > MAX_REQUEST_BODY_BYTES:
            raise RequestBodyError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"The JSON request body must not exceed {MAX_REQUEST_BODY_BYTES} bytes.",
            )
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestBodyError(
                HTTPStatus.BAD_REQUEST,
                "The JSON request body ended before Content-Length bytes arrived.",
            )
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestBodyError(
                HTTPStatus.BAD_REQUEST, "The request body must be a valid JSON object."
            ) from error
        if not isinstance(parsed, dict):
            raise RequestBodyError(
                HTTPStatus.BAD_REQUEST, "The request body must be a JSON object."
            )
        return parsed

    def write_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        content_type: str = "application/json",
    ) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_problem(
        self, status: HTTPStatus, code: str, title: str, detail: str
    ) -> None:
        self.write_json(
            {
                "type": f"https://id.registrystack.org/problems/solmara/{code.replace('.', '/')}",
                "title": title,
                "status": int(status),
                "code": code,
                "detail": detail,
            },
            status,
            content_type="application/problem+json",
        )

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("CHILD_BENEFIT_FEDERATOR_ACCESS_LOG", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            super().log_message(format, *args)


def collect_evidence(
    subject: str, claims: list[str], purpose: str, target: Any
) -> dict[str, Any]:
    by_claim: dict[str, dict[str, Any]] = {}
    source_trace: list[dict[str, Any]] = []
    for route in SOURCE_ROUTES:
        route_claims = [claim for claim in claims if claim in route["claims"]]
        if not route_claims:
            continue
        source = call_authority_notary(route, subject, route_claims, purpose)
        by_claim.update({result["claim_id"]: result for result in source["results"]})
        source_trace.append(source["trace"])
    return {
        "schema_version": API_VERSION,
        "evidence_set_id": f"cbe_{ulid()}",
        "orchestration": {
            "service_id": FEDERATOR_SERVICE_ID,
            "decision": "not_composed",
        },
        "purpose": purpose,
        "target": public_target(target),
        "results": [by_claim[claim] for claim in claims],
        "source_trace": source_trace,
    }


def call_authority_notary(
    route: dict[str, Any],
    subject: str,
    claims: list[str],
    purpose: str,
) -> dict[str, Any]:
    client_id = route["client_id"]
    token = service_token(client_id)
    if not token:
        raise AuthorityUpstreamError(
            route, None, f"missing_{service_token_env(client_id).lower()}"
        )
    url = service_url(client_id, "/v1/evaluations")
    body = evaluation_body(
        subject, claims, scheme="solmara_uin", format=CLAIM_RESULT_FORMAT
    )
    headers = auth_headers(token, purpose, CLAIM_RESULT_FORMAT)
    response = http_json("POST", url, headers, body)
    if response.status is None or not 200 <= response.status < 300:
        raise AuthorityUpstreamError(
            route, response.status, upstream_error_code(response)
        )
    results = minimized_results(route, claims, response)
    return {
        "results": results,
        "trace": {
            "authority": route["authority"],
            "service_id": authority_service_id(client_id),
            "claims": claims,
            "request_summary": {
                "method": "POST",
                "url": url,
                "purpose": purpose,
                "disclosure": "predicate",
                "claims": claims,
            },
            "response_summary": {
                "status": response.status,
                "headers": allowlisted_headers(response),
                "results": results,
            },
        },
    }


def minimized_results(
    route: dict[str, Any],
    requested: list[str],
    response: StepHttpResult,
) -> list[dict[str, Any]]:
    body = response.body if isinstance(response.body, dict) else {}
    raw_results = body.get("results")
    if not isinstance(raw_results, list):
        raise AuthorityUpstreamError(route, response.status, "invalid_response_payload")
    result_by_claim: dict[str, dict[str, Any]] = {}
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            raise AuthorityUpstreamError(route, response.status, "invalid_claim_result")
        claim_id = raw_result.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in result_by_claim:
            raise AuthorityUpstreamError(route, response.status, "invalid_claim_result")
        result_by_claim[claim_id] = raw_result
    if set(result_by_claim) != set(requested):
        raise AuthorityUpstreamError(route, response.status, "unexpected_claim_results")

    minimized: list[dict[str, Any]] = []
    for claim_id in requested:
        raw_result = result_by_claim[claim_id]
        satisfied = raw_result.get("satisfied")
        if (
            not isinstance(satisfied, bool)
            or raw_result.get("disclosure") != "predicate"
        ):
            raise AuthorityUpstreamError(route, response.status, "invalid_claim_result")
        minimized.append(
            {
                "claim_id": claim_id,
                "claim_version": raw_result.get("claim_version"),
                "satisfied": satisfied,
                "disclosure": "predicate",
                "format": CLAIM_RESULT_FORMAT,
                "issued_at": raw_result.get("issued_at"),
                "expires_at": raw_result.get("expires_at"),
                "authority": route["authority"],
                "notary_service_id": authority_service_id(route["client_id"]),
            }
        )
    return minimized


def upstream_error_code(response: StepHttpResult) -> str:
    body = response.body if isinstance(response.body, dict) else {}
    code = body.get("code") or body.get("error") or response.error
    return str(code) if code else f"http_{response.status}"


def allowlisted_headers(response: StepHttpResult) -> dict[str, str]:
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() in {"content-type", "www-authenticate"}
    }


def accepts_media_type(value: str, expected: str) -> bool:
    for item in value.split(","):
        media_type = item.split(";", 1)[0].strip().lower()
        if media_type in {expected.lower(), "application/*", "*/*"}:
            return True
    return False


def subject_id(body: dict[str, Any]) -> str:
    target = body.get("target") if isinstance(body.get("target"), dict) else {}
    identifiers = target.get("identifiers") if isinstance(target, dict) else []
    if not isinstance(identifiers, list):
        return ""
    for identifier in identifiers:
        if not isinstance(identifier, dict):
            continue
        if identifier.get("scheme") == "solmara_uin" and isinstance(
            identifier.get("value"), str
        ):
            return identifier["value"]
    return ""


def requested_claims(body: dict[str, Any]) -> list[str]:
    raw = body.get("claims")
    if not isinstance(raw, list):
        return []
    return [claim for claim in raw if isinstance(claim, str)]


def public_target(target: Any) -> dict[str, Any]:
    """Describe the target without echoing its raw identifier value."""
    if not isinstance(target, dict):
        return {}
    identifiers = target.get("identifiers")
    schemes = []
    if isinstance(identifiers, list):
        schemes = sorted(
            {
                identifier["scheme"]
                for identifier in identifiers
                if isinstance(identifier, dict)
                and isinstance(identifier.get("scheme"), str)
            }
        )
    public: dict[str, Any] = {"identifier_schemes": schemes}
    if isinstance(target.get("type"), str):
        public["type"] = target["type"]
    return public


def claim_catalog() -> dict[str, Any]:
    claims = [
        {
            "id": claim_id,
            "version": "1",
            "authority": route["authority"],
            "notary_service_id": authority_service_id(route["client_id"]),
            "disclosure": "predicate",
        }
        for claim_id, route in CLAIM_ROUTES.items()
    ]
    return {
        "schema_version": API_VERSION,
        "service_id": FEDERATOR_SERVICE_ID,
        "response_media_type": "application/json",
        "claims": claims,
        "data": claims,
        "composition": {
            "eligible-for-child-benefit": "not_returned_by_orchestrator",
            "owner": "child-benefit-programme-policy",
        },
    }


def path_parts(path: str) -> list[str]:
    parsed = urlparse(path)
    return [unquote(part) for part in parsed.path.split("/") if part]


def ulid() -> str:
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(ULID_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def main() -> int:
    host = os.environ.get("CHILD_BENEFIT_FEDERATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("CHILD_BENEFIT_FEDERATOR_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), ChildBenefitFederatorHandler)
    print(f"child-benefit-federator listening on http://{host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
