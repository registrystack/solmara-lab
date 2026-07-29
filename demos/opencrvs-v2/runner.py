#!/usr/bin/env python3
"""Run the optional OpenCRVS v2 interoperability proof without leaking source data."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "demos" / "opencrvs-v2"
AUTHORED_PROJECT = DEMO / "project"
RUNTIME = DEMO / ".runtime"
RUNTIME_PROJECT = RUNTIME / "project"
RUNTIME_ENV = RUNTIME / "local.env"
EVIDENCE_DIR = ROOT / "output" / "opencrvs-v2-demo"
EVIDENCE_PATH = EVIDENCE_DIR / "evidence.json"


def external_env_path() -> Path:
    override = os.environ.get("OPENCRVS_DEMO_ENV_FILE")
    if override:
        return Path(override).expanduser().resolve()
    for parent in (ROOT, *ROOT.parents):
        candidate = parent / "registry-internal" / ".env.opencrvs"
        if candidate.is_file():
            return candidate
    return ROOT.parent / "registry-internal" / ".env.opencrvs"


EXTERNAL_ENV = external_env_path()
PURPOSE = "https://id.registrystack.org/solmara/purpose/opencrvs-v2-birth-proof"
WRONG_PURPOSE = (
    "https://id.registrystack.org/solmara/purpose/opencrvs-v2-not-authorized"
)
RESULT_FORMAT = "application/vnd.registry-notary.claim-result+json"
CREDENTIAL_FORMAT = "application/dc+sd-jwt"
PROFILE = "opencrvs-birth-evidence.birth-predicates"
NOTARY_SERVICE_ID = "opencrvs-v2-demo-notary"
CREDENTIAL_ISSUER = "did:web:id.registrystack.org:solmara:authority:cra"
ISSUER_KID = f"{CREDENTIAL_ISSUER}#opencrvs-demo-issuer-key-1"
CREDENTIAL_VCT = (
    "https://id.registrystack.org/solmara/credential/opencrvs-v2-birth-proof/v1"
)
CLAIMS = [
    "birth-record-exists",
    "registration-number-matches",
    "child-national-id-matches",
    "mother-recorded-on-birth",
    "informant-is-mother",
]
NO_MATCH_RESULTS = {
    claim: False if claim == "birth-record-exists" else None for claim in CLAIMS
}
EXPECTED_OUTPUTS = {
    "child_national_id_matches": "boolean",
    "event_type_birth": "boolean",
    "informant_is_mother": "boolean",
    "mother_recorded_on_birth": "boolean",
    "registration_number_matches": "boolean",
    "tracking_id_matches": "boolean",
}
RUNTIME_ORIGIN_ACK = "OPENCRVS_DEMO_ALLOW_IGNORED_RUNTIME_ORIGINS"
SELECTOR_KEYS = {
    "registration_number": "OPENCRVS_DEMO_REGISTRATION_NUMBER",
    "child_national_id": "OPENCRVS_DEMO_CHILD_NATIONAL_ID",
    "tracking_id": "OPENCRVS_DEMO_TRACKING_ID",
}
SUPPORTED = [
    "OAuth-authenticated native OpenCRVS search",
    "bounded Relay/Rhai source adaptation",
    "exact record matching and ambiguity handling",
    "minimized scalar and predicate outputs",
    "Notary evaluation from Relay provenance",
    "holder-bound dc+sd-jwt issuance through /v1/credentials",
    "top-level scalar parent-related predicates",
]
NOT_DEMONSTRATED = [
    "structured parents[] or representative objects in a credential",
    "proof that the credential holder is the child's parent or informant",
    "registrar-initiated OID4VCI pre-authorized offers",
    "delivery into a parent's wallet",
    "OpenCRVS-triggered issuance",
    "unrelated unreleased structured-claim behavior",
    "official OpenCRVS compatibility certification",
]


class DemoFailure(RuntimeError):
    """A deliberately value-free error safe to print to an operator."""


@dataclass(frozen=True)
class HttpResult:
    status: int | None
    body: Any
    headers: Mapping[str, str]


@dataclass(frozen=True)
class ExampleSelectors:
    registration_number: str
    child_national_id: str
    tracking_id: str
    child_name: str | None = None


@dataclass(frozen=True)
class RelayActivity:
    completion_intents: int
    credential_dispatches: int
    data_dispatches: int


def exact_consultation_dispatch(
    before: RelayActivity, after: RelayActivity, label: str
) -> dict[str, int]:
    dispatch = {
        "credential_dispatch_delta": (
            after.credential_dispatches - before.credential_dispatches
        ),
        "source_data_dispatch_delta": (after.data_dispatches - before.data_dispatches),
    }
    if any(delta != 1 for delta in dispatch.values()):
        raise DemoFailure(
            f"the {label} consultation did not make exactly one credential "
            "and one source request"
        )
    return dispatch


def relay_rate_bound_evidence(
    public_bounds: Any, effective_limits: Any
) -> dict[str, dict[str, Any]]:
    if (
        not isinstance(public_bounds, dict)
        or not isinstance(effective_limits, dict)
        or effective_limits.get("quota_per_minute") != 4
        or effective_limits.get("quota_burst") != 2
        or effective_limits["quota_per_minute"]
        > public_bounds.get("quota_per_minute", 0)
        or effective_limits["quota_burst"] > public_bounds.get("quota_burst", 0)
    ):
        raise DemoFailure(
            "the compiled Relay rate limits do not preserve the demo's effective "
            "four-per-minute, burst-two contract"
        )
    return {
        "public_bounds": public_bounds,
        "effective_runtime_limits": effective_limits,
    }


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def read_dotenv(path: Path) -> dict[str, str]:
    """Parse the small dotenv subset used by the two runtime env files."""
    if not path.is_file():
        raise DemoFailure(f"required environment file is missing: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise DemoFailure(f"invalid environment assignment in {path.name}")
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is None:
            raise DemoFailure(f"invalid environment name in {path.name}")
        if len(value) >= 2 and value[:1] == value[-1:] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def required_external_env() -> tuple[dict[str, str], ExampleSelectors]:
    values = read_dotenv(EXTERNAL_ENV)
    for name in ("OPENCRVS_CLIENT_ID", "OPENCRVS_SECRET", "OPENCRVS_URL"):
        if not values.get(name):
            raise DemoFailure(f"{EXTERNAL_ENV} must define {name}")

    selectors = {
        field: os.environ.get(name) or values.get(name, "")
        for field, name in SELECTOR_KEYS.items()
    }
    child_name = (
        os.environ.get("OPENCRVS_DEMO_CHILD_NAME")
        or values.get("OPENCRVS_DEMO_CHILD_NAME")
        or None
    )
    # The current read-only operator file carries the example as a comment.
    # Use it only to fill missing selector values and strengthen the output scan.
    text = EXTERNAL_ENV.read_text(encoding="utf-8")
    match = re.search(
        r"child called (?P<name>[^:]+):\s*Tracking ID:\s*(?P<tracking>[A-Z0-9]{6}),"
        r"\s*Registration Number:\s*(?P<registration>[A-Z0-9]{12}),"
        r"\s*National ID:\s*(?P<nid>[0-9]{10})",
        text,
    )
    if match is not None:
        selectors = {
            "registration_number": selectors["registration_number"]
            or match.group("registration"),
            "child_national_id": selectors["child_national_id"] or match.group("nid"),
            "tracking_id": selectors["tracking_id"] or match.group("tracking"),
        }
        child_name = child_name or match.group("name").strip()
    if not all(selectors.values()):
        missing = [
            env_name
            for field, env_name in SELECTOR_KEYS.items()
            if not selectors[field]
        ]
        raise DemoFailure(
            f"{EXTERNAL_ENV} must define the demo selectors: {', '.join(missing)}"
        )
    if re.fullmatch(r"[A-Z0-9]{12}", selectors["registration_number"]) is None:
        raise DemoFailure("the demo registration selector has the wrong format")
    if re.fullmatch(r"[0-9]{10}", selectors["child_national_id"]) is None:
        raise DemoFailure("the demo national ID selector has the wrong format")
    if re.fullmatch(r"[A-Z0-9]{6}", selectors["tracking_id"]) is None:
        raise DemoFailure("the demo tracking selector has the wrong format")
    return values, ExampleSelectors(**selectors, child_name=child_name)


def opencrvs_host(raw: str) -> str:
    candidate = raw.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise DemoFailure("OPENCRVS_URL must be a path-free HTTPS DNS host")
    host = parsed.hostname
    raw_hostname = parsed.netloc.removesuffix(":443")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise DemoFailure("OPENCRVS_URL must be a DNS host, not an IP address")
    if raw_hostname != host or (
        re.fullmatch(
            r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
            host,
        )
        is None
    ):
        raise DemoFailure("OPENCRVS_URL must be a valid lowercase DNS host")
    return host


def run(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    expected_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=ROOT,
        env=dict(env) if env is not None else None,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if expected_failure:
        return result
    if result.returncode != 0:
        label = " ".join(
            Path(part).name if index == 0 else part
            for index, part in enumerate(command[:2])
        )
        raise DemoFailure(
            f"{label} failed; inspect the command locally with secrets redacted"
        )
    return result


def registryctl() -> str:
    override = os.environ.get("OPENCRVS_DEMO_REGISTRYCTL")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise DemoFailure("OPENCRVS_DEMO_REGISTRYCTL must name an executable file")
        return str(path)
    result = run([str(ROOT / "scripts" / "registryctl-pinned.sh"), "path"])
    path = result.stdout.strip()
    if not path:
        raise DemoFailure("the pinned registryctl helper returned no executable")
    return path


def registryctl_identity(versions: Mapping[str, str]) -> dict[str, Any]:
    executable = Path(registryctl()).resolve()
    version = run([str(executable), "--version"]).stdout.strip()
    executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    overridden = bool(os.environ.get("OPENCRVS_DEMO_REGISTRYCTL"))
    if not overridden:
        return {
            "version": version,
            "source_ref": versions["REGISTRY_STACK_SOURCE_REF"],
            "source_commit": versions["REGISTRY_STACK_SOURCE_COMMIT"],
            "executable_sha256": executable_sha256,
            "development_override": False,
        }
    source_commit = os.environ.get(
        "OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT",
        "",
    )
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise DemoFailure(
            "OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT must identify the exact "
            "development compiler commit"
        )
    repository_result = run(
        ["git", "-C", str(executable.parent), "rev-parse", "--show-toplevel"],
        expected_failure=True,
    )
    if repository_result.returncode != 0:
        raise DemoFailure(
            "the development registryctl must be inside its Registry Stack worktree"
        )
    repository = Path(repository_result.stdout.strip()).resolve()
    try:
        executable.relative_to(repository)
    except ValueError as error:
        raise DemoFailure(
            "the development registryctl is outside its reported Registry Stack worktree"
        ) from error
    actual_commit = run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"]
    ).stdout.strip()
    tracked_status = run(
        [
            "git",
            "-C",
            str(repository),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ]
    ).stdout.strip()
    if actual_commit != source_commit or tracked_status:
        raise DemoFailure(
            "the development registryctl source worktree must be clean at the exact "
            "declared commit"
        )
    return {
        "version": version,
        "source_commit": source_commit,
        "executable_sha256": executable_sha256,
        "development_override": True,
    }


def relay_runtime_identity(
    versions: Mapping[str, str],
    compiler: Mapping[str, Any],
) -> dict[str, Any]:
    image = os.environ.get("OPENCRVS_DEMO_RELAY_IMAGE", "")
    if not image:
        if compiler.get("development_override") is True:
            raise DemoFailure(
                "the development compiler requires OPENCRVS_DEMO_RELAY_IMAGE "
                "from the same Registry Stack candidate"
            )
        return {
            "version": versions["REGISTRYCTL_VERSION"],
            "source_ref": versions["REGISTRY_STACK_SOURCE_REF"],
            "source_commit": versions["REGISTRY_STACK_SOURCE_COMMIT"],
            "relay_image": versions["REGISTRY_RELAY_IMAGE"],
            "notary_image": versions["REGISTRY_NOTARY_IMAGE"],
            "development_override": False,
        }
    source_commit = os.environ.get("OPENCRVS_DEMO_RELAY_SOURCE_COMMIT", "")
    relay_platform = os.environ.get("OPENCRVS_DEMO_RELAY_PLATFORM", "")
    if (
        re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or relay_platform not in {"linux/amd64", "linux/arm64"}
        or compiler.get("development_override") is not True
        or compiler.get("source_commit") != source_commit
    ):
        raise DemoFailure(
            "the development Relay image, platform, and registryctl must declare "
            "one exact Registry Stack candidate"
        )
    relay_architecture = relay_platform.removeprefix("linux/")
    inspected = run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            (
                "{{.Id}}|{{.Architecture}}|"
                '{{index .Config.Labels "org.opencontainers.image.revision"}}|'
                '{{index .Config.Labels "org.registrystack.registry-relay.features"}}'
            ),
            image,
        ],
        expected_failure=True,
    )
    if inspected.returncode != 0:
        raise DemoFailure(
            "the declared development Relay image is not available locally"
        )
    parts = inspected.stdout.strip().split("|")
    if (
        len(parts) != 4
        or re.fullmatch(r"sha256:[0-9a-f]{64}", parts[0]) is None
        or parts[1] != relay_architecture
        or parts[2] != source_commit
        or parts[3] != "attribute-release,crosswalk-runtime"
    ):
        raise DemoFailure(
            "the development Relay image lacks the exact platform, source, or "
            "feature labels"
        )
    version = run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            relay_platform,
            "--entrypoint",
            "/usr/local/bin/registry-relay",
            image,
            "--version",
        ]
    ).stdout.strip()
    return {
        "version": version,
        "source_commit": source_commit,
        "relay_image": image,
        "relay_image_id": parts[0],
        "relay_platform": relay_platform,
        "notary_image": versions["REGISTRY_NOTARY_IMAGE"],
        "development_override": True,
    }


def registry_command(
    action: str,
    project: Path,
    *,
    environment: str | None = None,
    expected_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [registryctl(), action, "--project-dir", str(project)]
    if environment is not None:
        command.extend(["--environment", environment])
    if action in {"test", "build"}:
        command.extend(["--format", "json"])
    return run(command, expected_failure=expected_failure)


def parse_registry_report(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DemoFailure("registryctl returned an invalid JSON report") from error
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != "registryctl.project_command.v1"
    ):
        raise DemoFailure("registryctl returned an unsupported report")
    return report


def compiler_boundary() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for structured_type in ("object", "array"):
        with tempfile.TemporaryDirectory(prefix="opencrvs-v2-boundary-") as temporary:
            project = Path(temporary) / "project"
            shutil.copytree(
                AUTHORED_PROJECT,
                project,
                ignore=shutil.ignore_patterns(".registry-stack"),
            )
            path = project / "integrations" / "birth-record" / "integration.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["outputs"]["parents"] = {"type": structured_type}
            path.write_text(
                yaml.safe_dump(document, sort_keys=False),
                encoding="utf-8",
            )
            check = registry_command(
                "check", project, environment="local", expected_failure=True
            )
            results[f"structured_parents_{structured_type}"] = {
                "accepted": check.returncode == 0,
                "rejected_or_unsupported": check.returncode != 0,
                "diagnostic_persisted": False,
            }
    if not all(item["rejected_or_unsupported"] for item in results.values()):
        raise DemoFailure(
            "registryctl unexpectedly accepted a structured parents output"
        )
    return results


def invalid_selector_boundary() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opencrvs-v2-selector-") as temporary:
        project = Path(temporary) / "project"
        shutil.copytree(
            AUTHORED_PROJECT,
            project,
            ignore=shutil.ignore_patterns(".registry-stack"),
        )
        fixture = (
            project
            / "integrations"
            / "birth-record"
            / "fixtures"
            / "invalid-registration-number.yaml"
        )
        shutil.copy2(
            DEMO / "negative-fixtures" / "invalid-registration-number.yaml",
            fixture,
        )
        result = registry_command("test", project, expected_failure=True)
        if result.returncode == 0:
            raise DemoFailure(
                "registryctl unexpectedly accepted an invalid selector fixture"
            )
        return {
            "coverage": "authored synthetic fixture rejected by registryctl input validation",
            "rejected_before_execution": True,
            "source_access": False,
            "diagnostic_persisted": False,
        }


def compiled_integration_contract(build: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    pack = json.loads(
        (build / "reviewable" / "integration-packs" / "birth-record.json").read_text(
            encoding="utf-8"
        )
    )
    outputs = {
        name: definition.get("type")
        for name, definition in pack["spec"]["output"].items()
    }
    if outputs != EXPECTED_OUTPUTS:
        raise DemoFailure(
            "the compiled Relay output contract is not minimized as expected"
        )
    oauth_response = pack["spec"]["plan"]["credential_operation"]["response"]
    expected_oauth_response = {
        "accepted_statuses": [200],
        "access_token_max_bytes": 4096,
        "cache_mode": "disabled",
        "max_bytes": 8192,
        "schema": "strict_access_token_bearer_no_expiry",
        "token_type": "Bearer",
    }
    if oauth_response != expected_oauth_response:
        raise DemoFailure(
            "the compiled Relay OAuth response contract is not strict and non-caching"
        )
    private_binding = json.loads(
        (
            build
            / "private"
            / "relay"
            / "config"
            / "artifacts"
            / "private-bindings"
            / "opencrvs-birth-evidence-birth.json"
        ).read_text(encoding="utf-8")
    )
    if "max_token_lifetime_ms" in private_binding["limits"]:
        raise DemoFailure(
            "the no-expiry OAuth profile unexpectedly gained a cache lifetime"
        )
    return pack, oauth_response


def offline_checks() -> dict[str, Any]:
    test_report = parse_registry_report(registry_command("test", AUTHORED_PROJECT))
    fixtures = test_report.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise DemoFailure("registryctl reported no demo fixtures")
    if any(
        not isinstance(item, dict) or item.get("passed") is not True
        for item in fixtures
    ):
        raise DemoFailure("one or more Registry project fixture cases failed")
    registry_command("check", AUTHORED_PROJECT, environment="local")
    build_report = parse_registry_report(
        registry_command("build", AUTHORED_PROJECT, environment="local")
    )
    if build_report.get("status") != "built":
        raise DemoFailure("registryctl did not complete the demo build")
    _, oauth_response = compiled_integration_contract(
        AUTHORED_PROJECT / ".registry-stack" / "build" / "local"
    )
    return {
        "fixture_cases": len(fixtures),
        "all_passed": True,
        "oauth_response_profile": oauth_response,
        "invalid_selector": invalid_selector_boundary(),
        "structured_parent_boundary": compiler_boundary(),
    }


def generate_private_jwk(kid: str) -> str:
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes_raw()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return json.dumps(
        {
            "alg": "EdDSA",
            "crv": "Ed25519",
            "d": b64url(private),
            "kid": kid,
            "kty": "OKP",
            "x": b64url(public),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def fresh_runtime_values() -> dict[str, str]:
    caller = secrets.token_urlsafe(32)
    return {
        "POSTGRES_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD": secrets.token_urlsafe(32),
        "OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD": secrets.token_urlsafe(32),
        "OPENCRVS_RELAY_POSTGRES_READER_PASSWORD": secrets.token_urlsafe(32),
        "OPENCRVS_RELAY_AUDIT_HASH_SECRET": secrets.token_urlsafe(32),
        "OPENCRVS_RELAY_AUDIT_PSEUDONYM_EPOCH_1": secrets.token_urlsafe(32),
        "OPENCRVS_NOTARY_AUDIT_HASH_SECRET": secrets.token_urlsafe(32),
        "OPENCRVS_DEMO_CALLER_TOKEN": caller,
        "OPENCRVS_DEMO_CALLER_TOKEN_HASH": (
            "sha256:" + hashlib.sha256(caller.encode("ascii")).hexdigest()
        ),
        "OPENCRVS_RELAY_WORKLOAD_JWK": generate_private_jwk(
            "opencrvs-v2-demo-relay-workload-key-1"
        ),
        "OPENCRVS_DEMO_ISSUER_JWK": generate_private_jwk(ISSUER_KID),
    }


def write_runtime_env(values: Mapping[str, str]) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temporary = RUNTIME / "local.env.tmp"
    temporary.write_text(
        "".join(f"{name}={value}\n" for name, value in sorted(values.items())),
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(RUNTIME_ENV)


def ensure_postgres_tls() -> None:
    directory = RUNTIME / "postgres"
    certificate = directory / "server.crt"
    private_key = directory / "server.key"
    if certificate.is_file() and private_key.is_file():
        return
    directory.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=opencrvs-db",
            "-addext",
            "subjectAltName=DNS:opencrvs-db,IP:127.0.0.1",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ]
    )
    if result.returncode != 0 or not certificate.is_file() or not private_key.is_file():
        raise DemoFailure("the disposable PostgreSQL TLS material was not generated")
    private_key.chmod(0o600)
    certificate.chmod(0o644)


def prepare_runtime_project(host: str) -> None:
    if os.environ.get(RUNTIME_ORIGIN_ACK) != "yes":
        raise DemoFailure(
            f"set {RUNTIME_ORIGIN_ACK}=yes to acknowledge that Registry Stack "
            "0.15.2 writes the live origins into its ignored runtime closure"
        )
    if RUNTIME_PROJECT.exists():
        shutil.rmtree(RUNTIME_PROJECT)
    shutil.copytree(
        AUTHORED_PROJECT,
        RUNTIME_PROJECT,
        ignore=shutil.ignore_patterns(".registry-stack"),
    )
    environment_path = RUNTIME_PROJECT / "environments" / "local.yaml"
    environment = yaml.safe_load(environment_path.read_text(encoding="utf-8"))
    source = environment["integrations"]["birth-record"]["source"]
    source["origin"] = f"https://gateway.{host}"
    source["oauth"]["origin"] = f"https://auth.{host}"
    environment_path.write_text(
        yaml.safe_dump(environment, sort_keys=False),
        encoding="utf-8",
    )
    registry_command("check", RUNTIME_PROJECT, environment="local")
    report = parse_registry_report(
        registry_command("build", RUNTIME_PROJECT, environment="local")
    )
    if report.get("status") != "built":
        raise DemoFailure("registryctl did not build the runtime project")


def compose_project_name() -> str:
    suffix = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:10]
    return f"solmara-opencrvs-v2-{suffix}"


def compose_environment(
    external: Mapping[str, str] | None = None,
    runtime: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(read_dotenv(ROOT / "versions.env"))
    if runtime is not None:
        environment.update(runtime)
    if external is not None:
        for name in ("OPENCRVS_CLIENT_ID", "OPENCRVS_SECRET"):
            environment[name] = external[name]
    environment["OPENCRVS_RUNTIME_PROJECT_DIR"] = str(RUNTIME_PROJECT)
    environment["COMPOSE_PROJECT_NAME"] = compose_project_name()
    development_relay = os.environ.get("OPENCRVS_DEMO_RELAY_IMAGE")
    if development_relay:
        environment["REGISTRY_RELAY_IMAGE"] = development_relay
    return environment


def compose_command(*arguments: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / "versions.env"),
        "-f",
        str(DEMO / "compose.yaml"),
        *arguments,
    ]


def wait_ready(url: str, timeout: int = 150) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/ready", timeout=2) as response:
                if response.status in (200, 204):
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise DemoFailure("the OpenCRVS demo Notary did not become ready")


def notary_url() -> str:
    port = os.environ.get("OPENCRVS_DEMO_NOTARY_PORT", "4391")
    if re.fullmatch(r"[0-9]{1,5}", port) is None or not 1 <= int(port) <= 65535:
        raise DemoFailure("OPENCRVS_DEMO_NOTARY_PORT is invalid")
    return f"http://127.0.0.1:{port}"


def start_demo() -> None:
    external, _ = required_external_env()
    host = opencrvs_host(external["OPENCRVS_URL"])
    versions = read_dotenv(ROOT / "versions.env")
    compiler = registryctl_identity(versions)
    relay_runtime_identity(versions, compiler)
    runtime = (
        read_dotenv(RUNTIME_ENV) if RUNTIME_ENV.is_file() else fresh_runtime_values()
    )
    prepare_runtime_project(host)
    write_runtime_env(runtime)
    ensure_postgres_tls()
    environment = compose_environment(external, runtime)
    run(compose_command("up", "-d", "--build"), env=environment)
    wait_ready(notary_url())


def http_json(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: Any | None = None,
    *,
    form: Mapping[str, str] | None = None,
    timeout: float = 30,
) -> HttpResult:
    data: bytes | None = None
    request_headers = dict(headers)
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    if form is not None:
        data = urllib.parse.urlencode(form).encode("ascii")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request = urllib.request.Request(
        url,
        method=method,
        headers=request_headers,
        data=data,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
            response_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
        response_headers = {key.lower(): value for key, value in error.headers.items()}
    except (OSError, urllib.error.URLError) as error:
        raise DemoFailure(
            "an HTTP request failed before receiving a response"
        ) from error
    try:
        parsed: Any = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = None
    return HttpResult(status, parsed, response_headers)


def jwt_parts(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise DemoFailure("a compact JWT has the wrong shape")
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
        signature = b64url_decode(parts[2])
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DemoFailure("a compact JWT could not be decoded") from error
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise DemoFailure("a compact JWT contains non-object JSON")
    return header, payload, signature, f"{parts[0]}.{parts[1]}".encode("ascii")


def sanitized_oauth_claim(value: Any, client_id: str) -> Any:
    if isinstance(value, str):
        return value.replace(client_id, "[client-id-redacted]")
    if isinstance(value, list):
        return [sanitized_oauth_claim(item, client_id) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[unsupported-claim-shape]"


def oauth_probe(external: Mapping[str, str]) -> tuple[dict[str, Any], str]:
    host = opencrvs_host(external["OPENCRVS_URL"])
    response = http_json(
        "POST",
        f"https://auth.{host}/token",
        {"Accept": "application/json"},
        form={
            "client_id": external["OPENCRVS_CLIENT_ID"],
            "client_secret": external["OPENCRVS_SECRET"],
            "grant_type": "client_credentials",
        },
    )
    body = response.body if isinstance(response.body, dict) else {}
    token = body.get("access_token")
    if (
        response.status != 200
        or set(body) != {"access_token", "token_type"}
        or body.get("token_type") != "Bearer"
        or not isinstance(token, str)
        or not token
    ):
        raise DemoFailure(
            "the OpenCRVS OAuth probe did not return the strict no-expiry "
            "bearer response"
        )
    _, payload, _, _ = jwt_parts(token)
    issued = payload.get("iat")
    expires = payload.get("exp")
    lifetime = (
        expires - issued
        if isinstance(issued, int) and isinstance(expires, int) and expires > issued
        else None
    )
    client_id = external["OPENCRVS_CLIENT_ID"]
    return (
        {
            "status": response.status,
            "token_present": True,
            "lifetime_seconds": lifetime,
            "issuer": sanitized_oauth_claim(payload.get("iss"), client_id),
            "audience": sanitized_oauth_claim(payload.get("aud"), client_id),
            "scope": sanitized_oauth_claim(payload.get("scope"), client_id),
            "jwt_claims_parsed_without_signature_verification": True,
        },
        token,
    )


def evaluation_body(
    selectors: ExampleSelectors, registration: str | None = None
) -> dict[str, Any]:
    return {
        "target": {
            "type": "Person",
            "identifiers": [
                {
                    "scheme": "opencrvs_registration_number",
                    "value": registration or selectors.registration_number,
                },
                {
                    "scheme": "opencrvs_child_national_id",
                    "value": selectors.child_national_id,
                },
            ],
            "attributes": {
                "opencrvs_tracking_id": selectors.tracking_id,
            },
        },
        "claims": CLAIMS,
        "disclosure": "predicate",
        "format": RESULT_FORMAT,
    }


def api_headers(token: str, purpose: str) -> dict[str, str]:
    return {
        "Accept": RESULT_FORMAT,
        "Data-Purpose": purpose,
        "x-api-key": token,
    }


def safe_error(result: HttpResult) -> dict[str, Any]:
    body = result.body if isinstance(result.body, dict) else {}
    code = body.get("code")
    return {
        "status": result.status,
        "rejected": result.status is not None and result.status >= 400,
        "code": code if isinstance(code, str) else None,
    }


def relay_activity(environment: Mapping[str, str]) -> RelayActivity:
    result = run(
        compose_command(
            "exec",
            "--no-TTY",
            "opencrvs-db",
            "psql",
            "--username",
            "opencrvs_admin",
            "--dbname",
            "opencrvs_demo",
            "--tuples-only",
            "--no-align",
            "--command",
            "SELECT (SELECT count(*) FROM relay_state_private.consultation_completion_intent),"
            "(SELECT count(*) FROM relay_state_private.dispatch_permit "
            "WHERE kind = 'credential' AND dispatched_at IS NOT NULL),"
            "(SELECT count(*) FROM relay_state_private.dispatch_permit "
            "WHERE kind = 'data' AND dispatched_at IS NOT NULL);",
        ),
        env=environment,
    )
    match = re.fullmatch(
        r"\s*([0-9]+)\|([0-9]+)\|([0-9]+)\s*",
        result.stdout,
    )
    if match is None:
        raise DemoFailure("the Relay activity counters could not be read")
    return RelayActivity(
        completion_intents=int(match.group(1)),
        credential_dispatches=int(match.group(2)),
        data_dispatches=int(match.group(3)),
    )


def live_negative(
    url: str,
    headers: Mapping[str, str],
    body: Mapping[str, Any],
    environment: Mapping[str, str],
    *,
    expected_status: int,
    expected_code: str,
) -> dict[str, Any]:
    before = relay_activity(environment)
    result = http_json("POST", f"{url}/v1/evaluations", headers, body)
    after = relay_activity(environment)
    summary = safe_error(result)
    summary["credential_dispatch_delta"] = (
        after.credential_dispatches - before.credential_dispatches
    )
    summary["source_data_dispatch_delta"] = (
        after.data_dispatches - before.data_dispatches
    )
    if (
        summary["status"] != expected_status
        or summary["code"] != expected_code
        or summary["credential_dispatch_delta"] != 0
        or summary["source_data_dispatch_delta"] != 0
    ):
        raise DemoFailure("a live negative control crossed its expected boundary")
    return summary


def evaluation_summary(result: HttpResult) -> dict[str, Any]:
    if result.status != 200 or not isinstance(result.body, dict):
        summary = safe_error(result)
        code = summary["code"] or "no stable problem code"
        raise DemoFailure(f"Notary evaluation returned HTTP {result.status}: {code}")
    results = result.body.get("results")
    if not isinstance(results, list) or len(results) != len(CLAIMS):
        raise DemoFailure("Notary evaluation returned the wrong claim set")
    values: dict[str, bool | None] = {}
    for item in results:
        if not isinstance(item, dict) or item.get("claim_id") not in CLAIMS:
            raise DemoFailure("Notary evaluation returned an unknown claim")
        raw_value = item.get("satisfied", item.get("value"))
        if raw_value not in (True, False, None):
            raise DemoFailure("Notary evaluation returned a non-predicate result")
        values[item["claim_id"]] = raw_value
    if set(values) != set(CLAIMS):
        raise DemoFailure("Notary evaluation returned duplicate or missing claims")
    return {
        "status": result.status,
        "claim_ids": CLAIMS,
        "results": values,
    }


def require_no_match_contract(summary: Mapping[str, Any]) -> None:
    if summary.get("results") != NO_MATCH_RESULTS:
        raise DemoFailure("the nonexistent registration did not return exact no match")


def first_evaluation_id(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        for result in body["results"]:
            if isinstance(result, dict) and isinstance(
                result.get("evaluation_id"), str
            ):
                return result["evaluation_id"]
    raise DemoFailure("Notary evaluation returned no evaluation identifier")


def holder_material() -> tuple[str, Ed25519PrivateKey, dict[str, str]]:
    key = Ed25519PrivateKey.generate()
    public_bytes = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_jwk = {
        "crv": "Ed25519",
        "kty": "OKP",
        "x": b64url(public_bytes),
    }
    holder_id = "did:jwk:" + b64url(
        json.dumps(public_jwk, separators=(",", ":")).encode("utf-8")
    )
    return holder_id, key, public_jwk


def holder_proof(
    holder_id: str,
    key: Ed25519PrivateKey,
    evaluation_id: str,
) -> str:
    now = int(time.time())
    header = {"alg": "EdDSA", "kid": holder_id, "typ": "kb+jwt"}
    payload = {
        "aud": NOTARY_SERVICE_ID,
        "claims": CLAIMS,
        "credential_profile": PROFILE,
        "disclosure": b64url(hashlib.sha256(b"predicate").digest()),
        "evaluation_id": evaluation_id,
        "exp": now + 60,
        "iat": now,
        "jti": secrets.token_urlsafe(24),
        "sub": holder_id,
    }
    header_segment = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    return f"{signing_input.decode('ascii')}.{b64url(key.sign(signing_input))}"


def verify_sd_jwt(
    credential: str,
    issuer_private_jwk: str,
    holder_id: str,
    holder_public_jwk: Mapping[str, str],
) -> dict[str, Any]:
    compact, *disclosure_parts = credential.split("~")
    disclosures = [part for part in disclosure_parts if part]
    header, payload, signature, signing_input = jwt_parts(compact)
    try:
        issuer_jwk = json.loads(issuer_private_jwk)
        if (
            header.get("alg") != "EdDSA"
            or header.get("kid") != ISSUER_KID
            or issuer_jwk.get("kid") != ISSUER_KID
            or header.get("kid") != issuer_jwk.get("kid")
            or payload.get("_sd_alg") != "sha-256"
        ):
            raise DemoFailure("the SD-JWT protected metadata is invalid")
        public_key = Ed25519PrivateKey.from_private_bytes(
            b64url_decode(issuer_jwk["d"])
        ).public_key()
        public_key.verify(signature, signing_input)
    except (InvalidSignature, KeyError, ValueError, TypeError) as error:
        raise DemoFailure(
            "the issuer key or credential signature is invalid"
        ) from error
    digests = payload.get("_sd")
    if not isinstance(digests, list) or not all(
        isinstance(item, str) for item in digests
    ):
        raise DemoFailure("the SD-JWT has no valid disclosure digest set")
    computed = [
        b64url(hashlib.sha256(item.encode("ascii")).digest()) for item in disclosures
    ]
    if sorted(computed) != sorted(digests):
        raise DemoFailure("the returned disclosures do not match the SD-JWT digests")
    try:
        disclosed_claims: dict[str, Any] = {}
        for encoded in disclosures:
            disclosure = json.loads(b64url_decode(encoded))
            if (
                not isinstance(disclosure, list)
                or len(disclosure) != 3
                or not isinstance(disclosure[0], str)
                or not disclosure[0]
                or not isinstance(disclosure[1], str)
                or not isinstance(disclosure[2], dict)
                or disclosure[2].get("claim_id") != disclosure[1]
                or disclosure[2].get("value") is not True
                or disclosure[2].get("satisfied") is not True
                or disclosure[1] in disclosed_claims
            ):
                raise DemoFailure("the SD-JWT disclosure set is invalid")
            disclosed_claims[disclosure[1]] = True
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError) as error:
        raise DemoFailure("the SD-JWT disclosure set is invalid") from error
    if disclosed_claims != {claim: True for claim in CLAIMS}:
        raise DemoFailure(
            "the SD-JWT does not disclose the expected evaluated predicates"
        )
    if payload.get("iss") != CREDENTIAL_ISSUER or payload.get("vct") != CREDENTIAL_VCT:
        raise DemoFailure("the SD-JWT credential identity is invalid")
    confirmation = payload.get("cnf")
    if not isinstance(confirmation, dict):
        raise DemoFailure("the SD-JWT has no holder confirmation")
    if (
        confirmation.get("kid") != holder_id
        or confirmation.get("jwk") != holder_public_jwk
    ):
        raise DemoFailure(
            "the SD-JWT holder confirmation does not match the ephemeral holder"
        )
    issued = payload.get("iat")
    expires = payload.get("exp")
    if not isinstance(issued, int) or not isinstance(expires, int) or expires <= issued:
        raise DemoFailure("the SD-JWT lifetime is invalid")
    return {
        "format": CREDENTIAL_FORMAT,
        "vct": payload.get("vct"),
        "issuer": payload.get("iss"),
        "kid": header.get("kid"),
        "algorithm": header.get("alg"),
        "lifetime_seconds": expires - issued,
        "disclosure_count": len(disclosures),
        "issuer_signature_valid": True,
        "disclosures_match_digests": True,
        "disclosed_claims_verified": True,
        "holder_binding": "did:jwk",
        "cnf_matches_ephemeral_holder": True,
        "sha256": hashlib.sha256(credential.encode("utf-8")).hexdigest(),
    }


def issue_credential(
    url: str,
    caller_token: str,
    evaluation: HttpResult,
    issuer_private_jwk: str,
) -> tuple[dict[str, Any], str]:
    evaluation_id = first_evaluation_id(evaluation.body)
    holder_id, holder_key, holder_public_jwk = holder_material()
    proof = holder_proof(holder_id, holder_key, evaluation_id)
    body = {
        "claims": CLAIMS,
        "credential_profile": PROFILE,
        "disclosure": "predicate",
        "evaluation_id": evaluation_id,
        "format": CREDENTIAL_FORMAT,
        "holder": {
            "binding": "did",
            "id": holder_id,
            "proof": proof,
        },
        "purpose": PURPOSE,
    }
    response = http_json(
        "POST",
        f"{url}/v1/credentials",
        {
            "Accept": "application/json",
            "Data-Purpose": PURPOSE,
            "x-api-key": caller_token,
        },
        body,
    )
    response_body = response.body if isinstance(response.body, dict) else {}
    credential = response_body.get("credential")
    if response.status not in (200, 201) or not isinstance(credential, str):
        raise DemoFailure("Notary credential issuance did not succeed")
    returned_disclosures = response_body.get("disclosures")
    compact_disclosures = [part for part in credential.split("~")[1:] if part]
    if (
        not isinstance(returned_disclosures, list)
        or not all(isinstance(item, str) for item in returned_disclosures)
        or returned_disclosures != compact_disclosures
    ):
        raise DemoFailure(
            "Notary returned disclosures that differ from the compact credential"
        )
    verification = verify_sd_jwt(
        credential,
        issuer_private_jwk,
        holder_id,
        holder_public_jwk,
    )
    return {
        "status": response.status,
        **verification,
    }, credential


def compiled_artifacts() -> dict[str, Any]:
    build = RUNTIME_PROJECT / ".registry-stack" / "build" / "local"
    relay_config = yaml.safe_load(
        (build / "private" / "relay" / "config" / "relay-consultation.yaml").read_text(
            encoding="utf-8"
        )
    )
    pack_entry = relay_config["consultation"]["artifacts"]["integration_packs"][0]
    contract_entry = relay_config["consultation"]["artifacts"]["public_contracts"][0]
    private_entry = relay_config["consultation"]["artifacts"]["private_bindings"][0]
    private_binding = json.loads(
        (build / "private" / "relay" / "config" / private_entry["path"]).read_text(
            encoding="utf-8"
        )
    )
    pack, oauth_response = compiled_integration_contract(build)
    public_bounds = pack["spec"]["bounds"]
    effective_limits = private_binding.get("limits")
    rate_bounds = relay_rate_bound_evidence(public_bounds, effective_limits)
    outputs = {
        name: definition.get("type")
        for name, definition in pack["spec"]["output"].items()
    }
    return {
        "integration_pack": {
            "typed_hash": pack_entry["hash"],
            "artifact_sha256": pack_entry["sha256"],
        },
        "consultation_contract": {
            "typed_hash": contract_entry["hash"],
            "artifact_sha256": contract_entry["sha256"],
        },
        "relay": {
            "outcome": "match",
            "emitted_output_names_types": outputs,
            **rate_bounds,
            "oauth_response_profile": oauth_response,
            "cross_consultation_token_cache": False,
        },
    }


def scan_bytes(
    paths: Sequence[Path],
    additional: Sequence[bytes],
    sensitive: Mapping[str, bytes],
) -> dict[str, Any]:
    blobs: list[bytes] = list(additional)
    file_count = 0
    for path in paths:
        if not path.exists():
            continue
        for candidate in [path] if path.is_file() else path.rglob("*"):
            if candidate.is_file():
                blobs.append(candidate.read_bytes())
                file_count += 1
    for label, needle in sensitive.items():
        if needle and any(needle in blob for blob in blobs):
            raise DemoFailure(
                f"sensitive value detected during sanitized-output scan: {label}"
            )
    token_pattern = re.compile(
        rb"(?:Bearer\s+[A-Za-z0-9._~-]{20,}|"
        rb"eyJ[A-Za-z0-9_-]{12,}\.eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,})"
    )
    if any(token_pattern.search(blob) for blob in blobs):
        raise DemoFailure(
            "a bearer-shaped token was detected during sanitized-output scan"
        )
    return {
        "passed": True,
        "files_scanned": file_count,
        "memory_blobs_scanned": len(additional),
    }


def proof() -> None:
    external, selectors = required_external_env()
    runtime = read_dotenv(RUNTIME_ENV)
    environment = compose_environment(external, runtime)
    wait_ready(notary_url(), timeout=10)
    offline = offline_checks()
    oauth, oauth_token = oauth_probe(external)
    url = notary_url()
    caller_token = runtime["OPENCRVS_DEMO_CALLER_TOKEN"]
    request_body = evaluation_body(selectors)

    wrong_caller = live_negative(
        url,
        api_headers(secrets.token_urlsafe(32), PURPOSE),
        request_body,
        environment,
        expected_status=401,
        expected_code="auth.missing_credential",
    )
    wrong_purpose = live_negative(
        url,
        api_headers(caller_token, WRONG_PURPOSE),
        request_body,
        environment,
        expected_status=403,
        expected_code="purpose.not_allowed",
    )
    invalid_body = evaluation_body(selectors)
    invalid_body["target"]["identifiers"][0]["value"] = "INVALID"
    invalid_selector = live_negative(
        url,
        api_headers(caller_token, PURPOSE),
        invalid_body,
        environment,
        expected_status=409,
        expected_code="evidence.not_available",
    )

    before_positive = relay_activity(environment)
    positive = http_json(
        "POST",
        f"{url}/v1/evaluations",
        api_headers(caller_token, PURPOSE),
        request_body,
    )
    after_positive = relay_activity(environment)
    positive_summary = evaluation_summary(positive)
    if not all(value is True for value in positive_summary["results"].values()):
        raise DemoFailure("the known OpenCRVS record did not satisfy every predicate")
    positive_dispatch = exact_consultation_dispatch(
        before_positive, after_positive, "known-record"
    )

    credential_summary, raw_credential = issue_credential(
        url,
        caller_token,
        positive,
        runtime["OPENCRVS_DEMO_ISSUER_JWK"],
    )

    nonexistent_body = evaluation_body(selectors, registration="ZZZZZZZZZZZZ")
    before_missing = relay_activity(environment)
    missing = http_json(
        "POST",
        f"{url}/v1/evaluations",
        api_headers(caller_token, PURPOSE),
        nonexistent_body,
    )
    after_missing = relay_activity(environment)
    missing_summary = evaluation_summary(missing)
    require_no_match_contract(missing_summary)
    missing_dispatch = exact_consultation_dispatch(
        before_missing, after_missing, "no-match"
    )

    logs = run(compose_command("logs", "--no-color"), env=environment).stdout.encode(
        "utf-8"
    )
    versions = read_dotenv(ROOT / "versions.env")
    compiler = registryctl_identity(versions)
    registry_runtime = relay_runtime_identity(versions, compiler)
    artifacts = compiled_artifacts()
    evidence: dict[str, Any] = {
        "schema_version": "solmara.opencrvs-v2-demo.evidence.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "registry_stack": {
            "runtime": registry_runtime,
            "authoring_compiler": compiler,
        },
        "oauth": oauth,
        "opencrvs_search": {
            "endpoint_path": "/events/events/search",
            "http_status": 200,
            "result_count": 1,
            "event_type": "birth",
            "known_registration_number_matched": True,
            "known_tracking_id_matched": True,
            "observation": (
                "Inferred from the live Relay match. The reviewed adapter returns match "
                "only after HTTP 200, one result, birth type, and exact tracking binding."
            ),
        },
        "compiled_artifacts": {
            "integration_pack": artifacts["integration_pack"],
            "consultation_contract": artifacts["consultation_contract"],
        },
        "relay": {
            **artifacts["relay"],
            "known_record_dispatch": positive_dispatch,
        },
        "notary_evaluation": positive_summary,
        "credential_issuance": credential_summary,
        "negative_controls": {
            "wrong_caller": wrong_caller,
            "wrong_purpose": wrong_purpose,
            "invalid_selector": invalid_selector,
            "syntactically_valid_nonexistent_registration": {
                **missing_summary,
                **missing_dispatch,
            },
        },
        "offline_evidence": offline,
        "persistence": {
            "raw_opencrvs_response_written": False,
            "bearer_token_written": False,
            "holder_private_key_written": False,
            "credential_written": False,
        },
        "capability_boundary": {
            "supported_and_demonstrated": SUPPORTED,
            "not_demonstrated_or_unavailable": NOT_DEMONSTRATED,
            "release_boundary": (
                "The released v0.15.2 decoder recognizes strict no-expiry OAuth, "
                "but its durable completion-seed contract cannot admit this script "
                "plan, and its worker budget charges Relay-owned source waits. "
                "Development proof uses exact-commit Registry Stack compiler and "
                "Relay candidates. Pin the next Registry Stack release before "
                "deployment."
            ),
            "issuance_boundary": (
                "Direct authenticated machine API issuance to a demo-controlled "
                "ephemeral holder key. This is not an OID4VCI registrar offer and "
                "does not prove that the holder is a parent or informant."
            ),
        },
    }
    encoded = json.dumps(evidence, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    sensitive: dict[str, bytes] = {
        "OpenCRVS client id": external["OPENCRVS_CLIENT_ID"].encode("utf-8"),
        "OpenCRVS client secret": external["OPENCRVS_SECRET"].encode("utf-8"),
        "OAuth access token": oauth_token.encode("utf-8"),
        "credential": raw_credential.encode("utf-8"),
        "registration number": selectors.registration_number.encode("utf-8"),
        "child national id": selectors.child_national_id.encode("utf-8"),
        "tracking id": selectors.tracking_id.encode("utf-8"),
    }
    if selectors.child_name:
        sensitive["child name"] = selectors.child_name.encode("utf-8")
    scan = scan_bytes(
        [
            RUNTIME_PROJECT / ".registry-stack" / "build" / "local",
            EVIDENCE_DIR,
        ],
        [logs, encoded],
        sensitive,
    )
    evidence["sanitized_output_scan"] = scan
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_DIR / "evidence.json.tmp"
    temporary.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(EVIDENCE_PATH)
    print(f"sanitized evidence written to {EVIDENCE_PATH.relative_to(ROOT)}")


def compose_config() -> None:
    validation_runtime = {
        "POSTGRES_ADMIN_PASSWORD": "v" * 40,
        "OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD": "r" * 40,
        "OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD": "m" * 40,
        "OPENCRVS_RELAY_POSTGRES_READER_PASSWORD": "d" * 40,
        "OPENCRVS_RELAY_AUDIT_HASH_SECRET": "a" * 40,
        "OPENCRVS_RELAY_AUDIT_PSEUDONYM_EPOCH_1": "p" * 40,
        "OPENCRVS_NOTARY_AUDIT_HASH_SECRET": "n" * 40,
        "OPENCRVS_DEMO_CALLER_TOKEN_HASH": "sha256:" + "0" * 64,
        "OPENCRVS_RELAY_WORKLOAD_JWK": "{}",
        "OPENCRVS_DEMO_ISSUER_JWK": "{}",
    }
    validation_external = {
        "OPENCRVS_CLIENT_ID": "compose-validation-only",
        "OPENCRVS_SECRET": "compose-validation-only",
    }
    run(
        compose_command("config", "--quiet"),
        env=compose_environment(validation_external, validation_runtime),
    )


def down() -> None:
    run(
        compose_command("down", "-v", "--remove-orphans"),
        env=compose_environment(),
    )
    if RUNTIME.exists():
        resolved = RUNTIME.resolve()
        if resolved.parent != DEMO.resolve() or resolved.name != ".runtime":
            raise DemoFailure("refusing to remove an unexpected runtime path")
        shutil.rmtree(resolved)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("offline", "compose-config", "up", "proof", "down"),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "offline":
            report = offline_checks()
            print(
                f"OpenCRVS demo offline checks passed: "
                f"{report['fixture_cases']} fixture cases"
            )
        elif args.action == "compose-config":
            compose_config()
            print("OpenCRVS demo Compose configuration is valid")
        elif args.action == "up":
            start_demo()
            print("OpenCRVS demo is ready")
        elif args.action == "proof":
            proof()
        elif args.action == "down":
            down()
            print(
                "OpenCRVS demo containers, volumes, and ignored runtime closure removed"
            )
    except DemoFailure as error:
        print(f"opencrvs-v2 demo: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
