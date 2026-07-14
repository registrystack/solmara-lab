#!/usr/bin/env python3
"""Public hosted smoke checks for Solmara Lab."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOMAIN = "solmara.registrystack.org"
EXPECTED_SCENARIOS = {
    "birth-to-child-benefit",
    "death-to-pension-survivor",
    "farmer-climate-smart-voucher",
    "citizen-self-service",
}
EXPECTED_CHILD_BENEFIT_CLAIMS = {
    "birth-is-registered",
    "population-record-active",
    "child-age-under-5",
    "household-below-poverty-threshold",
    "not-already-enrolled",
}
EXPECTED_CHILD_BENEFIT_NOTARIES = {
    "civil-child-benefit-notary",
    "nia-child-benefit-notary",
    "sro-child-benefit-notary",
    "programme-child-benefit-notary",
}


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    base_url: str
    health_path: str = "/healthz"
    env_name: str | None = None


@dataclass(frozen=True)
class HostedTargets:
    home_url: str
    portal_url: str
    metadata_url: str
    esignet_url: str
    esignet_ui_url: str
    wallet_url: str
    relays: tuple[ServiceTarget, ...]
    notaries: tuple[ServiceTarget, ...]


class SmokeFailure(Exception):
    """A stable smoke failure with a short operator-facing message."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    targets = default_targets(args.domain, args.scheme)
    env = hosted_env(os.environ, targets)
    env["SOLMARA_SMOKE_READY_TIMEOUT_SECONDS"] = str(args.timeout)

    checks: list[tuple[str, Any]] = [
        ("public routes and service health", lambda: check_public_routes(targets, args.timeout)),
        ("Visitor Center scenario runner proxy", lambda: check_home_demo(targets.home_url, args.timeout)),
        ("OID4VCI wallet issuer", lambda: check_oid4vci_issuer(targets, args.timeout)),
        (
            "eSignet backend",
            lambda: run_command(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "smoke-esignet.py"),
                    "--relay-url",
                    relay_url(targets, "SOLMARA_NIA_RELAY_URL"),
                    "--esignet-url",
                    targets.esignet_url,
                    "--esignet-ui-url",
                    targets.esignet_ui_url,
                ],
                env,
                cwd=ROOT,
            ),
        ),
        (
            "Relay source endpoints",
            lambda: run_command(
                [sys.executable, str(ROOT / "scripts" / "smoke-relay-sources.py")],
                env,
                cwd=ROOT,
            ),
        ),
        (
            "Notary scenario evaluations",
            lambda: run_command(
                [sys.executable, str(ROOT / "scripts" / "smoke-live.py")],
                env,
                cwd=ROOT,
            ),
        ),
        (
            "published demo token refusals",
            lambda: run_command(
                [sys.executable, str(ROOT / "scripts" / "smoke-published-tokens.py")],
                env,
                cwd=ROOT,
            ),
        ),
        (
            "portal live BFF",
            lambda: run_command(
                [sys.executable, str(ROOT / "scripts" / "smoke-portal-compose.py")],
                env,
                cwd=ROOT,
            ),
        ),
    ]

    if args.browser:
        checks.extend(
            [
                (
                    "Visitor Center browser e2e",
                    lambda: run_command(
                        ["pnpm", "e2e"],
                        {**env, "SOLMARA_HOME_E2E_MODE": "live", "PLAYWRIGHT_BASE_URL": targets.home_url},
                        cwd=ROOT / "home",
                    ),
                ),
                (
                    "portal browser e2e",
                    lambda: run_command(
                        ["pnpm", "e2e"],
                        {
                            **env,
                            "SOLMARA_PORTAL_E2E_MODE": "hosted",
                            "PLAYWRIGHT_BASE_URL": targets.portal_url,
                        },
                        cwd=ROOT / "portal",
                    ),
                ),
            ]
        )

    for name, check in checks:
        print(f"check: {name}", flush=True)
        try:
            check()
        except SmokeFailure as error:
            print(f"FAILED: {name}: {error}", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as error:
            print(f"FAILED: {name}: command exited {error.returncode}", file=sys.stderr)
            return error.returncode or 1

    suffix = " with browser e2e" if args.browser else ""
    print(f"smoke-hosted: Solmara hosted smoke passed{suffix}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        default=os.environ.get("SOLMARA_HOSTED_DOMAIN", DEFAULT_DOMAIN),
        help=f"root hosted domain, default {DEFAULT_DOMAIN}",
    )
    parser.add_argument(
        "--scheme",
        default=os.environ.get("SOLMARA_HOSTED_SCHEME", "https"),
        choices=("http", "https"),
        help="public URL scheme, default https",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("SOLMARA_SMOKE_READY_TIMEOUT_SECONDS", "90")),
        help="seconds to wait for each public endpoint",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        default=truthy(os.environ.get("SOLMARA_HOSTED_SMOKE_BROWSER")),
        help="also run hosted Playwright e2e for the Visitor Center and portal",
    )
    return parser.parse_args(argv)


def normalize_argv(argv: list[str]) -> list[str]:
    return argv[1:] if argv[:1] == ["--"] else argv


def default_targets(domain: str, scheme: str = "https") -> HostedTargets:
    clean_domain = normalize_domain(domain)

    def public_url(host: str) -> str:
        return f"{scheme}://{host}"

    def subdomain(name: str) -> str:
        return public_url(f"{name}.{clean_domain}")

    return HostedTargets(
        home_url=public_url(clean_domain),
        portal_url=subdomain("portal"),
        metadata_url=subdomain("metadata"),
        esignet_url=subdomain("esignet"),
        esignet_ui_url=subdomain("esignet-ui"),
        wallet_url=subdomain("wallet"),
        relays=(
            ServiceTarget("CRA civil relay", subdomain("cra-relay"), env_name="SOLMARA_CRA_RELAY_URL"),
            ServiceTarget("NIA population relay", subdomain("nia-relay"), env_name="SOLMARA_NIA_RELAY_URL"),
            ServiceTarget("SRO social relay", subdomain("sro-relay"), env_name="SOLMARA_SRO_RELAY_URL"),
            ServiceTarget(
                "Programme MIS relay",
                subdomain("mosd-programme-relay"),
                env_name="SOLMARA_PROGRAMME_RELAY_URL",
            ),
            ServiceTarget("SIPF pensions relay", subdomain("sipf-relay"), env_name="SOLMARA_SIPF_RELAY_URL"),
            ServiceTarget("NAgDI agriculture relay", subdomain("nagdi-relay"), env_name="SOLMARA_NAGDI_RELAY_URL"),
        ),
        notaries=(
            ServiceTarget(
                "child benefit federator",
                subdomain("child-benefit-federator"),
                env_name="CHILD_BENEFIT_FEDERATOR_URL",
            ),
            ServiceTarget(
                "CRA child benefit notary",
                subdomain("civil-child-benefit-notary"),
                env_name="CIVIL_CHILD_BENEFIT_NOTARY_URL",
            ),
            ServiceTarget(
                "NIA child benefit notary",
                subdomain("nia-child-benefit-notary"),
                env_name="NIA_CHILD_BENEFIT_NOTARY_URL",
            ),
            ServiceTarget(
                "SRO child benefit notary",
                subdomain("sro-child-benefit-notary"),
                env_name="SRO_CHILD_BENEFIT_NOTARY_URL",
            ),
            ServiceTarget(
                "programme child benefit notary",
                subdomain("programme-child-benefit-notary"),
                env_name="PROGRAMME_CHILD_BENEFIT_NOTARY_URL",
            ),
            ServiceTarget("pension notary", subdomain("pension-notary"), env_name="PENSION_NOTARY_URL"),
            ServiceTarget("NAgDI notary", subdomain("nagdi-notary"), env_name="NAGDI_NOTARY_URL"),
            ServiceTarget(
                "citizen services notary",
                subdomain("citizen-notary"),
                env_name="PORTAL_CITIZEN_NOTARY_URL",
            ),
            ServiceTarget(
                "citizen OID4VCI issuer notary",
                subdomain("citizen-issuer-notary"),
                env_name="CITIZEN_ISSUER_NOTARY_URL",
            ),
        ),
    )


def normalize_domain(domain: str) -> str:
    clean = domain.strip()
    if clean.startswith("http://"):
        clean = clean.removeprefix("http://")
    if clean.startswith("https://"):
        clean = clean.removeprefix("https://")
    return clean.strip("/")


def hosted_env(base_env: os._Environ[str] | dict[str, str], targets: HostedTargets) -> dict[str, str]:
    env = dict(base_env)
    env.update(
        {
            "PORTAL_URL": targets.portal_url,
            "SOLMARA_PORTAL_URL": targets.portal_url,
            "STATIC_METADATA_URL": targets.metadata_url,
            "PORTAL_CIVIL_RELAY_URL": relay_url(targets, "SOLMARA_CRA_RELAY_URL"),
            "PORTAL_SOCIAL_RELAY_URL": relay_url(targets, "SOLMARA_SRO_RELAY_URL"),
            "PORTAL_AGRI_RELAY_URL": relay_url(targets, "SOLMARA_NAGDI_RELAY_URL"),
            "PORTAL_CERTS_RELAY_URL": relay_url(targets, "SOLMARA_CRA_RELAY_URL"),
            "SOLMARA_ESIGNET_PUBLIC_BASE_URL": targets.esignet_url,
            "SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL": targets.esignet_ui_url,
            "SOLMARA_WALLET_URL": targets.wallet_url,
            "SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED": "1",
        }
    )
    for target in (*targets.relays, *targets.notaries):
        if target.env_name:
            env[target.env_name] = target.base_url
    return env


def relay_url(targets: HostedTargets, env_name: str) -> str:
    for relay in targets.relays:
        if relay.env_name == env_name:
            return relay.base_url
    raise SmokeFailure(f"missing relay target for {env_name}")


def notary_url(targets: HostedTargets, env_name: str) -> str:
    for notary in targets.notaries:
        if notary.env_name == env_name:
            return notary.base_url
    raise SmokeFailure(f"missing notary target for {env_name}")


def check_public_routes(targets: HostedTargets, timeout: float) -> None:
    checks = [
        ServiceTarget("Visitor Center", targets.home_url, "/"),
        ServiceTarget("portal", targets.portal_url, "/"),
        ServiceTarget("Walt wallet", targets.wallet_url, "/"),
        ServiceTarget("static metadata", targets.metadata_url, "/metadata/index.json"),
        *targets.relays,
        *targets.notaries,
    ]
    failures: list[str] = []
    for target in checks:
        url = joined_url(target.base_url, target.health_path)
        result = wait_for_http("GET", url, timeout=timeout)
        if not result.ok:
            failures.append(f"{target.name} at {url}: {result.detail}")
    if failures:
        raise SmokeFailure("; ".join(failures))


def check_home_demo(home_url: str, timeout: float) -> None:
    scenarios = request_json("GET", joined_url(home_url, "/api/scenarios"), timeout=timeout)
    if scenarios.status != 200:
        raise SmokeFailure(f"/api/scenarios returned {scenarios.detail}")
    scenario_body = scenarios.body if isinstance(scenarios.body, dict) else {}
    scenario_items = scenario_body.get("scenarios", [])
    scenario_ids = {
        item.get("id")
        for item in scenario_items
        if isinstance(item, dict)
    }
    missing = sorted(EXPECTED_SCENARIOS - scenario_ids)
    if missing:
        raise SmokeFailure(f"/api/scenarios missing {', '.join(missing)}")

    positive = request_json(
        "POST",
        joined_url(home_url, "/api/scenarios/birth-to-child-benefit/steps/positive/run"),
        body={},
        timeout=timeout,
    )
    positive_result = result_payload(positive)
    positive_status = nested(positive_result, "response_source", "status")
    if positive.status != 200 or positive_status != 200:
        raise SmokeFailure(f"child positive step returned outer={positive.status}, inner={positive_status}")
    positive_body = nested(positive_result, "response_source", "body")
    if not isinstance(positive_body, dict):
        raise SmokeFailure("child positive step did not return a predicate bundle")
    federator = positive_body.get("federator")
    if not isinstance(federator, dict) or federator.get("service_id") != "child-benefit-federator":
        raise SmokeFailure("child positive step did not identify the public federator")
    if federator.get("decision") != "not_composed":
        raise SmokeFailure("child positive step composed an eligibility decision")
    results = positive_body.get("results")
    claim_ids = {
        result.get("claim_id")
        for result in results
        if isinstance(result, dict) and isinstance(result.get("claim_id"), str)
    } if isinstance(results, list) else set()
    if claim_ids != EXPECTED_CHILD_BENEFIT_CLAIMS:
        raise SmokeFailure(f"child positive step returned unexpected predicates, claim_ids={sorted(claim_ids)!r}")
    if "eligible-for-child-benefit" in claim_ids:
        raise SmokeFailure("child positive step returned a composed eligibility claim")
    trace = positive_body.get("federation_trace")
    source_notaries = {
        item.get("service_id")
        for item in trace
        if isinstance(item, dict) and isinstance(item.get("service_id"), str)
    } if isinstance(trace, list) else set()
    if source_notaries != EXPECTED_CHILD_BENEFIT_NOTARIES:
        raise SmokeFailure(
            f"child positive step returned an incomplete federation trace, source_notaries={sorted(source_notaries)!r}"
        )
    if "credential" in positive_result:
        raise SmokeFailure("child positive step unexpectedly issued a credential")

    denial = request_json(
        "POST",
        joined_url(home_url, "/api/scenarios/birth-to-child-benefit/steps/purpose-denial/run"),
        body={},
        timeout=timeout,
    )
    denial_result = result_payload(denial)
    denial_status = nested(denial_result, "response_source", "status")
    denial_code = nested(denial_result, "response_source", "body", "code")
    if denial.status != 200 or not isinstance(denial_status, int) or not 400 <= denial_status < 500:
        raise SmokeFailure(f"child purpose-denial step returned outer={denial.status}, inner={denial_status}")
    if not denial_code:
        raise SmokeFailure("child purpose-denial step did not return a stable problem code")


def check_oid4vci_issuer(targets: HostedTargets, timeout: float) -> None:
    issuer_url = notary_url(targets, "CITIZEN_ISSUER_NOTARY_URL")
    config_id = "citizen_status_sd_jwt"
    vct = joined_url(issuer_url, "/credentials/citizen-status/v1")
    metadata = request_json("GET", joined_url(issuer_url, "/.well-known/openid-credential-issuer"), timeout=timeout)
    if metadata.status != 200 or not isinstance(metadata.body, dict):
        raise SmokeFailure(f"OID4VCI issuer metadata returned {metadata.detail}")
    if metadata.body.get("credential_issuer") != issuer_url:
        raise SmokeFailure("OID4VCI metadata advertises the wrong credential_issuer")
    if metadata.body.get("credential_endpoint") != joined_url(issuer_url, "/oid4vci/credential"):
        raise SmokeFailure("OID4VCI metadata advertises the wrong credential_endpoint")
    if metadata.body.get("nonce_endpoint") != joined_url(issuer_url, "/oid4vci/nonce"):
        raise SmokeFailure("OID4VCI metadata advertises the wrong nonce_endpoint")
    if metadata.body.get("token_endpoint") != joined_url(issuer_url, "/oid4vci/token"):
        raise SmokeFailure("OID4VCI metadata is missing the pre-authorized-code token endpoint")
    if targets.esignet_url not in (metadata.body.get("authorization_servers") or []):
        raise SmokeFailure("OID4VCI metadata does not advertise Solmara eSignet as an authorization server")

    configs = metadata.body.get("credential_configurations_supported")
    if not isinstance(configs, dict) or config_id not in configs:
        raise SmokeFailure(f"OID4VCI metadata missing {config_id}")
    config = configs[config_id]
    if not isinstance(config, dict):
        raise SmokeFailure(f"OID4VCI metadata for {config_id} is not an object")
    if config.get("format") != "dc+sd-jwt":
        raise SmokeFailure(f"OID4VCI {config_id} format is {config.get('format')!r}")
    if config.get("vct") != vct:
        raise SmokeFailure(f"OID4VCI {config_id} vct is {config.get('vct')!r}")
    if "did:jwk" not in (config.get("cryptographic_binding_methods_supported") or []):
        raise SmokeFailure(f"OID4VCI {config_id} does not allow did:jwk holder binding")
    if "EdDSA" not in (config.get("credential_signing_alg_values_supported") or []):
        raise SmokeFailure(f"OID4VCI {config_id} does not advertise EdDSA credential signing")
    proof_jwt = nested(config, "proof_types_supported", "jwt", "proof_signing_alg_values_supported")
    if not isinstance(proof_jwt, list) or "EdDSA" not in proof_jwt:
        raise SmokeFailure(f"OID4VCI {config_id} does not advertise EdDSA proof signing")

    type_metadata = request_json(
        "GET",
        joined_url(issuer_url, "/.well-known/vct/credentials/citizen-status/v1"),
        timeout=timeout,
    )
    if type_metadata.status != 200 or not isinstance(type_metadata.body, dict):
        raise SmokeFailure(f"OID4VCI VCT metadata returned {type_metadata.detail}")
    if type_metadata.body.get("vct") != vct:
        raise SmokeFailure("OID4VCI VCT metadata advertises the wrong vct")

    offer = request_json(
        "GET",
        joined_url(issuer_url, f"/oid4vci/credential-offer?credential_configuration_id={config_id}"),
        timeout=timeout,
    )
    if offer.status != 200 or not isinstance(offer.body, dict):
        raise SmokeFailure(f"OID4VCI credential offer returned {offer.detail}")
    ids = offer.body.get("credential_configuration_ids")
    if ids != [config_id]:
        raise SmokeFailure(f"OID4VCI credential offer has unexpected credential_configuration_ids={ids!r}")

    unknown_offer = request_json(
        "GET",
        joined_url(issuer_url, "/oid4vci/credential-offer?credential_configuration_id=unknown"),
        timeout=timeout,
    )
    if unknown_offer.status != 400:
        raise SmokeFailure(f"OID4VCI unknown credential offer returned {unknown_offer.detail}")

    nonce = request_json(
        "POST",
        joined_url(issuer_url, "/oid4vci/nonce"),
        body={"credential_configuration_id": config_id},
        timeout=timeout,
    )
    if nonce.status != 200 or not isinstance(nonce.body, dict) or not nonce.body.get("c_nonce"):
        raise SmokeFailure(f"OID4VCI nonce returned {nonce.detail}")

    start = request_no_redirect(
        "GET",
        joined_url(issuer_url, f"/oid4vci/offer/start?credential_configuration_id={config_id}"),
        timeout=timeout,
    )
    if start.status not in {302, 303} or not start.location:
        raise SmokeFailure(f"OID4VCI offer start did not redirect, status={start.detail}")
    if not start.location.startswith(f"{targets.esignet_ui_url}/"):
        raise SmokeFailure("OID4VCI offer start redirected outside the Solmara eSignet UI")

    credential = request_json("POST", joined_url(issuer_url, "/oid4vci/credential"), body={}, timeout=timeout)
    if credential.status is None or credential.status < 400 or credential.status > 499:
        raise SmokeFailure(f"OID4VCI credential endpoint without bearer returned {credential.detail}")


def result_payload(response: "HttpResult") -> dict[str, Any]:
    if response.status != 200 or not isinstance(response.body, dict):
        raise SmokeFailure(f"scenario step returned {response.detail}")
    result = response.body.get("result")
    if not isinstance(result, dict):
        raise SmokeFailure("scenario step response missing result object")
    return result


@dataclass(frozen=True)
class HttpResult:
    status: int | None
    body: Any
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def detail(self) -> str:
        if self.status is not None:
            return f"HTTP {self.status}"
        return self.error or "no response"


@dataclass(frozen=True)
class RedirectResult:
    status: int | None
    location: str | None = None
    error: str = ""

    @property
    def detail(self) -> str:
        if self.status is not None:
            return f"HTTP {self.status}"
        return self.error or "no response"


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def wait_for_http(method: str, url: str, timeout: float) -> HttpResult:
    deadline = time.monotonic() + timeout
    last = HttpResult(None, {}, "timeout")
    while time.monotonic() < deadline:
        last = request_json(method, url, timeout=min(8.0, max(1.0, timeout)))
        if last.ok:
            return last
        time.sleep(1)
    return last


def request_json(method: str, url: str, body: Any | None = None, timeout: float = 8.0) -> HttpResult:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "solmara-hosted-smoke/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(response.status, parse_body(response.read()))
    except urllib.error.HTTPError as error:
        body = parse_body(error.read())
        error.close()
        return HttpResult(error.code, body)
    except Exception as error:  # noqa: BLE001
        return HttpResult(None, {}, error.__class__.__name__)


def request_no_redirect(method: str, url: str, timeout: float = 8.0) -> RedirectResult:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "solmara-hosted-smoke/1.0"},
        method=method,
    )
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return RedirectResult(response.status, response.headers.get("Location"))
    except urllib.error.HTTPError as error:
        location = error.headers.get("Location")
        error.close()
        return RedirectResult(error.code, location)
    except Exception as error:  # noqa: BLE001
        return RedirectResult(None, None, error.__class__.__name__)


def parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def joined_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def run_command(command: list[str], env: dict[str, str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def truthy(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
