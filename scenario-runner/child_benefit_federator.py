#!/usr/bin/env python3
"""Child benefit federation service for the Solmara lab.

The service is deliberately not an eligibility engine. It accepts one
purpose-limited child-benefit evidence request, sends signed Registry Notary
federation requests to source-owned Notaries, and returns the predicate bundle
and trace.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scenarios.common import CLAIM_RESULT_FORMAT, FEDERATED_BUNDLE_FORMAT, PURPOSES


API_VERSION = "solmara-child-benefit-federator/v1"
FEDERATION_PROTOCOL = "registry-notary-federation/v0.1"
FEDERATION_REQUEST_TYP = "registry-notary-request+jwt"
FEDERATION_RESPONSE_TYP = "registry-notary-response+jwt"
FEDERATOR_SERVICE_ID = "child-benefit-federator"
PUBLIC_DOMAIN = os.environ.get("CHILD_BENEFIT_PUBLIC_DOMAIN", "lab.registrystack.org")
FEDERATOR_PUBLIC_HOST = f"{FEDERATOR_SERVICE_ID}.{PUBLIC_DOMAIN}"
FEDERATOR_NODE_ID = f"did:web:{FEDERATOR_PUBLIC_HOST}"
FEDERATOR_ISSUER = f"https://{FEDERATOR_PUBLIC_HOST}"
FEDERATOR_JWK_ENV = "CHILD_BENEFIT_FEDERATOR_REQUEST_JWK"
FEDERATOR_TOKEN_ENV = "CHILD_BENEFIT_FEDERATOR_TOKEN"
CHILD_PURPOSE = PURPOSES["child_benefit"]
SUPPORTED_DISCLOSURES = {"predicate"}
SENSITIVE_RAW_CLAIMS = {"household-poverty-score", "household-profile"}
ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
MAX_REQUEST_BODY_BYTES = 64 * 1024
MAX_RESPONSE_LIFETIME_SECONDS = 300
ALLOWED_CLOCK_SKEW_SECONDS = 60


CLAIM_ROUTES: dict[str, dict[str, str]] = {
    "birth-is-registered": {
        "claim_id": "birth-is-registered",
        "authority": "Civil Registration Authority",
        "service_id": "civil-child-benefit-notary",
        "url_env": "CIVIL_CHILD_BENEFIT_NOTARY_URL",
        "default_url": "http://127.0.0.1:4325",
        "profile": "birth_is_registered",
        "node_id": f"did:web:civil-child-benefit-notary.{PUBLIC_DOMAIN}",
        "issuer": f"https://civil-child-benefit-notary.{PUBLIC_DOMAIN}",
    },
    "population-record-active": {
        "claim_id": "population-record-active",
        "authority": "National Identity Agency",
        "service_id": "nia-child-benefit-notary",
        "url_env": "NIA_CHILD_BENEFIT_NOTARY_URL",
        "default_url": "http://127.0.0.1:4326",
        "profile": "population_record_active",
        "node_id": f"did:web:nia-child-benefit-notary.{PUBLIC_DOMAIN}",
        "issuer": f"https://nia-child-benefit-notary.{PUBLIC_DOMAIN}",
    },
    "child-age-under-5": {
        "claim_id": "child-age-under-5",
        "authority": "Civil Registration Authority",
        "service_id": "civil-child-benefit-notary",
        "url_env": "CIVIL_CHILD_BENEFIT_NOTARY_URL",
        "default_url": "http://127.0.0.1:4325",
        "profile": "child_age_under_5",
        "node_id": f"did:web:civil-child-benefit-notary.{PUBLIC_DOMAIN}",
        "issuer": f"https://civil-child-benefit-notary.{PUBLIC_DOMAIN}",
    },
    "household-below-poverty-threshold": {
        "claim_id": "household-below-poverty-threshold",
        "authority": "Social Registry Office",
        "service_id": "sro-child-benefit-notary",
        "url_env": "SRO_CHILD_BENEFIT_NOTARY_URL",
        "default_url": "http://127.0.0.1:4327",
        "profile": "household_below_poverty_threshold",
        "node_id": f"did:web:sro-child-benefit-notary.{PUBLIC_DOMAIN}",
        "issuer": f"https://sro-child-benefit-notary.{PUBLIC_DOMAIN}",
    },
    "not-already-enrolled": {
        "claim_id": "not-already-enrolled",
        "authority": "MoSD Programme MIS",
        "service_id": "programme-child-benefit-notary",
        "url_env": "PROGRAMME_CHILD_BENEFIT_NOTARY_URL",
        "default_url": "http://127.0.0.1:4328",
        "profile": "not_already_enrolled",
        "node_id": f"did:web:programme-child-benefit-notary.{PUBLIC_DOMAIN}",
        "issuer": f"https://programme-child-benefit-notary.{PUBLIC_DOMAIN}",
    },
}


class RequestBodyError(Exception):
    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class FederationUpstreamError(Exception):
    def __init__(self, route: dict[str, str], status: int | None, code: str) -> None:
        super().__init__(code)
        self.route = route
        self.status = status
        self.code = code


class ChildBenefitFederatorHandler(BaseHTTPRequestHandler):
    server_version = "SolmaraChildBenefitFederator/1.0"

    def do_GET(self) -> None:
        parts = path_parts(self.path)
        if parts in (["health"], ["healthz"]):
            self.write_json({"status": "ok", "service": FEDERATOR_SERVICE_ID})
            return
        if parts == [".well-known", "jwks.json"]:
            self.write_json(public_jwks())
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
                    "This federator only serves the child-benefit-review purpose.",
                )
                return
            self.write_json(claim_catalog())
            return
        self.write_problem(HTTPStatus.NOT_FOUND, "not_found", "Not found", "No such federator route.")

    def do_POST(self) -> None:
        parts = path_parts(self.path)
        if parts not in (["v1", "evaluations"], ["v1", "federated-evaluations"]):
            self.write_problem(HTTPStatus.NOT_FOUND, "not_found", "Not found", "No such federator route.")
            return
        if not self.require_token():
            return
        purpose = self.headers.get("Data-Purpose", "")
        if purpose != CHILD_PURPOSE:
            self.write_problem(
                HTTPStatus.FORBIDDEN,
                "pdp.purpose_not_permitted",
                "Purpose not permitted",
                "This federator only serves the child-benefit-review purpose.",
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

        subject = subject_id(body)
        requested = requested_claims(body)
        if any(claim in SENSITIVE_RAW_CLAIMS for claim in requested):
            self.write_problem(
                HTTPStatus.FORBIDDEN,
                "pdp.purpose_not_permitted",
                "Disclosure not permitted",
                "Raw source fields are not available through this purpose.",
            )
            return
        if body.get("format") != FEDERATED_BUNDLE_FORMAT:
            self.write_problem(
                HTTPStatus.BAD_REQUEST,
                "request.unsupported_format",
                "Unsupported response format",
                f"Set format to {FEDERATED_BUNDLE_FORMAT}.",
            )
            return
        if not accepts_media_type(self.headers.get("Accept", ""), FEDERATED_BUNDLE_FORMAT):
            self.write_problem(
                HTTPStatus.NOT_ACCEPTABLE,
                "request.not_acceptable",
                "Unsupported response representation",
                f"Set Accept to {FEDERATED_BUNDLE_FORMAT}.",
            )
            return
        unknown = [claim for claim in requested if claim not in CLAIM_ROUTES]
        if not subject or not requested or unknown or len(requested) != len(set(requested)):
            detail = "The request must name a supported child-benefit predicate and solmara_uin target."
            self.write_problem(HTTPStatus.BAD_REQUEST, "request.invalid", "Invalid evidence request", detail)
            return

        try:
            bundle = evaluate_bundle(subject, requested, purpose, body.get("target"))
        except FederationUpstreamError as error:
            self.write_problem(
                HTTPStatus.BAD_GATEWAY,
                "federation.upstream_failed",
                "Authority evidence unavailable",
                f'{error.route["authority"]} did not return a valid signed predicate response.',
            )
            return
        self.write_json(bundle, content_type=FEDERATED_BUNDLE_FORMAT)

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
            raise RequestBodyError(HTTPStatus.BAD_REQUEST, "Content-Length must be a decimal byte count.") from error
        if length <= 0:
            raise RequestBodyError(HTTPStatus.BAD_REQUEST, "A non-empty JSON request body is required.")
        if length > MAX_REQUEST_BODY_BYTES:
            raise RequestBodyError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"The JSON request body must not exceed {MAX_REQUEST_BODY_BYTES} bytes.",
            )
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestBodyError(HTTPStatus.BAD_REQUEST, "The JSON request body ended before Content-Length bytes arrived.")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestBodyError(HTTPStatus.BAD_REQUEST, "The request body must be a valid JSON object.") from error
        if not isinstance(parsed, dict):
            raise RequestBodyError(HTTPStatus.BAD_REQUEST, "The request body must be a JSON object.")
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

    def write_problem(self, status: HTTPStatus, code: str, title: str, detail: str) -> None:
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
        if os.environ.get("CHILD_BENEFIT_FEDERATOR_ACCESS_LOG", "").lower() in {"1", "true", "yes"}:
            super().log_message(format, *args)


def evaluate_bundle(subject: str, claims: list[str], purpose: str, target: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    for claim_id in claims:
        route = CLAIM_ROUTES[claim_id]
        peer = call_peer_notary(route, subject, purpose)
        results.append(peer["result"])
        trace.append(peer["trace"])
    return {
        "schema_version": API_VERSION,
        "bundle_id": f"fcb_{ulid()}",
        "federator": {
            "service_id": FEDERATOR_SERVICE_ID,
            "issuer": FEDERATOR_ISSUER,
            "decision": "not_composed",
        },
        "purpose": purpose,
        "target": target,
        "results": results,
        "federation_trace": trace,
    }


def call_peer_notary(route: dict[str, str], subject: str, purpose: str) -> dict[str, Any]:
    url = joined_url(os.environ.get(route["url_env"], route["default_url"]), "/federation/v1/evaluations")
    jti = ulid()
    payload = federation_payload(route, subject, purpose, jti)
    token = sign_jwt(payload)
    request_source = {
        "method": "POST",
        "url": url,
        "headers": {"Content-Type": "application/jwt"},
        "body": payload,
    }
    status, headers, body = post_jwt(url, token)
    if status != 200:
        raise FederationUpstreamError(route, status, "peer_http_error")
    if not isinstance(body, str):
        raise FederationUpstreamError(route, status, "unsigned_peer_response")
    decoded = verify_peer_response(route, jti, body, headers.get("content-type", ""))
    if verification_error_code(decoded):
        raise FederationUpstreamError(route, status, verification_error_code(decoded) or "response_verification_failed")
    result = result_from_peer(route, decoded)
    return {
        "result": result,
        "trace": {
            "authority": route["authority"],
            "service_id": route["service_id"],
            "claim_id": route["claim_id"],
            "profile": route["profile"],
            "request_source": request_source,
            "response_source": {
                "status": status,
                "headers": {key: value for key, value in headers.items() if key in {"content-type", "www-authenticate"}},
                "body": verified_response_summary(route, decoded),
            },
        },
    }


def result_from_peer(route: dict[str, str], body: Any) -> dict[str, Any]:
    claim_id = route["claim_id"]
    issued_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    base = {
        "claim_id": claim_id,
        "claim_version": "2026-07",
        "format": CLAIM_RESULT_FORMAT,
        "issued_at": issued_at,
        "notary_service_id": route["service_id"],
        "authority": route["authority"],
        "federation_profile": route["profile"],
    }
    if not isinstance(body, dict):
        raise FederationUpstreamError(route, 200, "invalid_response_payload")
    result = body.get("result")
    claims = result.get("claims") if isinstance(result, dict) else None
    peer_claim = claims.get(claim_id) if isinstance(claims, dict) else None
    if not isinstance(peer_claim, dict):
        raise FederationUpstreamError(route, 200, "missing_claim_result")
    satisfied = peer_claim.get("satisfied")
    if not isinstance(satisfied, bool) or peer_claim.get("disclosure") != "predicate":
        raise FederationUpstreamError(route, 200, "invalid_claim_result")
    return {
        **base,
        "satisfied": satisfied,
        "value": satisfied,
        "disclosure": "predicate",
        "federation": {
            "issuer": body.get("iss"),
            "subject": body.get("sub"),
            "request_jti": body.get("request_jti"),
            "profile": body.get("profile"),
        },
    }


def verified_response_summary(route: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    """Return an allowlisted trace of the verified peer response.

    Authority responses can add pairwise subject references, evaluation ids,
    source timestamps, or future fields. Those values are authenticated, but
    they are not part of the federator's disclosure contract and must not cross
    the public trace boundary.
    """
    result = body.get("result")
    claims = result.get("claims") if isinstance(result, dict) else None
    peer_claim = claims.get(route["claim_id"]) if isinstance(claims, dict) else None
    return {
        "signature_verified": True,
        "issuer": body.get("iss"),
        "subject": body.get("sub"),
        "audience": body.get("aud"),
        "protocol": body.get("protocol"),
        "action": body.get("action"),
        "profile": body.get("profile"),
        "request_jti": body.get("request_jti"),
        "response_jti": body.get("jti"),
        "issued_at": body.get("iat"),
        "not_before": body.get("nbf"),
        "expires_at": body.get("exp"),
        "claim": {
            "claim_id": route["claim_id"],
            "satisfied": peer_claim.get("satisfied") if isinstance(peer_claim, dict) else None,
            "disclosure": peer_claim.get("disclosure") if isinstance(peer_claim, dict) else None,
        },
    }


def federation_payload(route: dict[str, str], subject: str, purpose: str, jti: str) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": FEDERATOR_ISSUER,
        "sub": FEDERATOR_NODE_ID,
        "aud": route["node_id"],
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "jti": jti,
        "protocol": FEDERATION_PROTOCOL,
        "action": "evaluate",
        "profile": route["profile"],
        "purpose": purpose,
        "request": {
            "subject": {"id": subject, "id_type": "solmara_uin"},
            "claims": [route["claim_id"]],
        },
    }


def post_jwt(url: str, token: str, timeout: float = 8.0) -> tuple[int | None, dict[str, str], Any]:
    request = urllib.request.Request(
        url,
        headers={"Content-Type": "application/jwt", "Accept": "application/jwt, application/json"},
        data=token.encode("ascii"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, {key.lower(): value for key, value in response.headers.items()}, parse_body(raw)
    except urllib.error.HTTPError as error:
        return error.code, {key.lower(): value for key, value in error.headers.items()}, parse_body(error.read())
    except Exception as error:
        return None, {}, {"error": error.__class__.__name__}


def verify_peer_response(route: dict[str, str], request_jti: str, token: str, content_type: str) -> Any:
    if content_type.split(";", 1)[0].strip().lower() != "application/jwt":
        return verification_error("unexpected_content_type")
    parts = token.split(".")
    if len(parts) != 3:
        return verification_error("invalid_compact_jwt")
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
        signature = b64url_decode(parts[2])
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return verification_error("invalid_jwt_encoding")
    if not isinstance(header, dict) or not isinstance(payload, dict):
        return verification_error("invalid_jwt_json")
    if header.get("alg") != "EdDSA" or header.get("typ") != FEDERATION_RESPONSE_TYP:
        return verification_error("unexpected_jwt_header")

    public_jwk = jwk_for_kid(route, header.get("kid"))
    if not public_jwk:
        return verification_error("unknown_response_key")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(b64url_decode(public_jwk["x"]))
        public_key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"))
    except (InvalidSignature, KeyError, ValueError):
        return verification_error("bad_response_signature")

    now = int(time.time())
    if payload.get("iss") != route["issuer"]:
        return verification_error("unexpected_issuer")
    if payload.get("sub") != route["node_id"]:
        return verification_error("unexpected_subject")
    if payload.get("aud") != FEDERATOR_NODE_ID:
        return verification_error("unexpected_audience")
    if payload.get("request_jti") != request_jti:
        return verification_error("unexpected_request_jti")
    if payload.get("protocol") != FEDERATION_PROTOCOL or payload.get("action") != "evaluate":
        return verification_error("unexpected_protocol")
    if payload.get("profile") != route["profile"]:
        return verification_error("unexpected_profile")
    if not all(type(payload.get(name)) is int for name in ("iat", "nbf", "exp")):
        return verification_error("invalid_response_lifetime")
    if not is_ulid(payload.get("jti")):
        return verification_error("invalid_response_jti")
    iat = payload["iat"]
    nbf = payload["nbf"]
    exp = payload["exp"]
    if exp <= iat or exp - iat > MAX_RESPONSE_LIFETIME_SECONDS or nbf > exp:
        return verification_error("invalid_response_lifetime")
    if iat > now + ALLOWED_CLOCK_SKEW_SECONDS:
        return verification_error("response_issued_in_future")
    if nbf > now + ALLOWED_CLOCK_SKEW_SECONDS:
        return verification_error("response_not_yet_valid")
    if exp <= now - ALLOWED_CLOCK_SKEW_SECONDS:
        return verification_error("response_expired")
    return payload


def jwk_for_kid(route: dict[str, str], kid: Any) -> dict[str, str] | None:
    if not isinstance(kid, str) or not kid:
        return None
    url = joined_url(os.environ.get(route["url_env"], route["default_url"]), "/.well-known/evidence/jwks.json")
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            jwks = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        return None
    for key in keys:
        if not isinstance(key, dict):
            continue
        if key.get("kid") == kid and key.get("kty") == "OKP" and key.get("crv") == "Ed25519":
            return {name: str(value) for name, value in key.items() if isinstance(value, str)}
    return None


def verification_error(code: str) -> dict[str, Any]:
    return {
        "error": {
            "type": "urn:solmara:problem:federation-response-verification",
            "title": "Federated Notary response verification failed",
            "code": code,
        }
    }


def verification_error_code(payload: Any) -> str | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None
    code = payload["error"].get("code")
    return code if isinstance(code, str) and code else "response_verification_failed"


def parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


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
        if identifier.get("scheme") == "solmara_uin" and isinstance(identifier.get("value"), str):
            return identifier["value"]
    return ""


def requested_claims(body: dict[str, Any]) -> list[str]:
    raw = body.get("claims")
    if not isinstance(raw, list):
        return []
    return [claim for claim in raw if isinstance(claim, str)]


def claim_catalog() -> dict[str, Any]:
    claims = [
        {
            "id": claim_id,
            "version": "2026-07",
            "authority": route["authority"],
            "notary_service_id": route["service_id"],
            "federation_profile": route["profile"],
            "disclosure": "predicate",
        }
        for claim_id, route in CLAIM_ROUTES.items()
    ]
    return {
        "schema_version": API_VERSION,
        "service_id": FEDERATOR_SERVICE_ID,
        "bundle_media_type": FEDERATED_BUNDLE_FORMAT,
        "claims": claims,
        "data": claims,
        "composition": {
            "eligible-for-child-benefit": "not_returned_by_federator",
            "owner": "child-benefit-programme-policy",
        },
    }


def sign_jwt(payload: dict[str, Any]) -> str:
    jwk = private_jwk()
    header = {"alg": "EdDSA", "typ": FEDERATION_REQUEST_TYP, "kid": jwk["kid"]}
    signing_input = f"{json_b64url(header)}.{json_b64url(payload)}"
    private_key = Ed25519PrivateKey.from_private_bytes(b64url_decode(jwk["d"]))
    signature = private_key.sign(signing_input.encode("ascii"))
    return f"{signing_input}.{b64url_nopad(signature)}"


def public_jwks() -> dict[str, Any]:
    jwk = private_jwk()
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": jwk["kid"],
                "alg": "EdDSA",
                "x": jwk["x"],
            }
        ]
    }


def private_jwk() -> dict[str, str]:
    raw = os.environ.get(FEDERATOR_JWK_ENV, "")
    if not raw:
        raise RuntimeError(f"{FEDERATOR_JWK_ENV} is not configured")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{FEDERATOR_JWK_ENV} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{FEDERATOR_JWK_ENV} is not a JWK object")
    required = ("kid", "x", "d")
    if parsed.get("kty") != "OKP" or parsed.get("crv") != "Ed25519" or not all(
        isinstance(parsed.get(key), str) and parsed[key] for key in required
    ):
        raise RuntimeError(f"{FEDERATOR_JWK_ENV} must be a private Ed25519 JWK with kid, x, and d")
    expected_kid = f"{FEDERATOR_NODE_ID}#request-key-1"
    if parsed["kid"] != expected_kid:
        raise RuntimeError(
            f"{FEDERATOR_JWK_ENV} kid must be {expected_kid}; generate secrets with "
            f"CHILD_BENEFIT_PUBLIC_DOMAIN={PUBLIC_DOMAIN}"
        )
    return {key: str(parsed[key]) for key in required}


def decode_jwt_payload(token: str) -> Any:
    parts = token.split(".")
    if len(parts) != 3:
        return {"error": "invalid_compact_jwt"}
    try:
        return json.loads(b64url_decode(parts[1]))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {"error": "invalid_jwt_payload"}


def ulid() -> str:
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(ULID_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def is_ulid(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 26 and all(character in ULID_ALPHABET for character in value)


def joined_url(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def path_parts(path: str) -> list[str]:
    parsed = urlparse(path)
    return [unquote(part) for part in parsed.path.split("/") if part]


def json_b64url(value: Any) -> str:
    return b64url_nopad(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def main() -> int:
    host = os.environ.get("CHILD_BENEFIT_FEDERATOR_HOST", "0.0.0.0")
    port = int(os.environ.get("CHILD_BENEFIT_FEDERATOR_PORT", "8080"))
    private_jwk()
    server = ThreadingHTTPServer((host, port), ChildBenefitFederatorHandler)
    print(f"child-benefit-federator listening on http://{host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
