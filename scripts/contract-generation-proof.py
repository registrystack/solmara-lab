#!/usr/bin/env python3
"""Prove a compiler-generated SRO Relay/Notary blue-green transition.

The proof is intentionally bounded to one authority. It compiles two complete
generations with the pinned registryctl, rejects the mixed pair during Notary
activation, and then activates the complete successor generation.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "sro-social"
PURPOSE = "https://id.registrystack.org/solmara/purpose/child-benefit-review"
CLAIM_ID = "household-below-poverty-threshold"
BLUE_SUBJECT = "2300027390"
GREEN_SUBJECT = "2300018263"
RESULT_FORMAT = "application/vnd.registry-notary.claim-result+json"
SENSITIVE_ENV_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "JWK")
MAX_DIAGNOSTIC_LINES = 12
MAX_DIAGNOSTIC_LINE_BYTES = 256
MAX_DIAGNOSTIC_BYTES = 4096
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class ProofFailure(RuntimeError):
    """A bounded proof assertion failed."""


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        parts = shlex.split(raw_value, posix=True)
        if len(parts) > 1:
            raise ProofFailure(f"{path.name} contains an invalid value for {name.strip()}")
        values[name.strip()] = parts[0] if parts else ""
    return values


def diagnostic_environment(environment: Mapping[str, str] | None) -> dict[str, str]:
    return dict(os.environ if environment is None else environment)


def bounded_redacted_output(
    output: str, environment: Mapping[str, str] | None
) -> str:
    redacted = output
    values = [BLUE_SUBJECT, GREEN_SUBJECT]
    values.extend(
        value
        for name, value in diagnostic_environment(environment).items()
        if value and any(marker in name for marker in SENSITIVE_ENV_MARKERS)
    )
    for value in sorted(set(values), key=len, reverse=True):
        redacted = redacted.replace(value, "[redacted]")
    redacted = ANSI_ESCAPE.sub("", redacted)
    lines = [
        "".join(
            character
            if character.isprintable() or character == "\t"
            else "?"
            for character in line
        )
        for line in redacted.splitlines()
    ]
    if not lines:
        return "(no command output captured)"
    if len(lines) > MAX_DIAGNOSTIC_LINES:
        lines = [*lines[:6], "... output lines omitted ...", *lines[-5:]]
    bounded_lines = []
    for line in lines:
        encoded = line.encode("utf-8")
        if len(encoded) > MAX_DIAGNOSTIC_LINE_BYTES:
            line = encoded[:MAX_DIAGNOSTIC_LINE_BYTES].decode("utf-8", errors="ignore")
            line += "..."
        bounded_lines.append(line)
    bounded = "\n".join(bounded_lines)
    encoded = bounded.encode("utf-8")
    if len(encoded) > MAX_DIAGNOSTIC_BYTES:
        bounded = encoded[:MAX_DIAGNOSTIC_BYTES].decode("utf-8", errors="ignore")
    return bounded


def command_failure(
    executable: str,
    returncode: int,
    output: str,
    environment: Mapping[str, str] | None,
) -> ProofFailure:
    diagnostic = bounded_redacted_output(output, environment)
    return ProofFailure(
        f"{Path(executable).name} command failed with exit {returncode}\n"
        f"command output (redacted and bounded):\n{diagnostic}"
    )


def run(
    arguments: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
    timeout: int = 240,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(arguments),
        cwd=ROOT,
        env=dict(environment) if environment is not None else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise command_failure(arguments[0], result.returncode, result.stdout, environment)
    return result


def preserve_cleanup_failure(
    cleanup: Callable[[], subprocess.CompletedProcess[str]],
    *,
    environment: Mapping[str, str] | None,
    primary_failure_active: bool,
) -> None:
    failure: ProofFailure | None = None
    try:
        result = cleanup()
    except subprocess.TimeoutExpired:
        failure = ProofFailure("docker Compose cleanup timed out")
    except OSError:
        failure = ProofFailure("docker Compose cleanup could not start")
    else:
        if result.returncode != 0:
            failure = command_failure(
                "docker compose cleanup",
                result.returncode,
                result.stdout,
                environment,
            )
    if failure is None:
        return
    if primary_failure_active:
        print(
            f"contract-generation-proof: secondary cleanup failure: {failure}",
            file=sys.stderr,
        )
        return
    raise failure


def make_successor(project: Path) -> None:
    integration = project / "integrations" / "child-benefit-household-by-uin" / "integration.yaml"
    document = yaml.safe_load(integration.read_text(encoding="utf-8"))
    if document.get("id") != "child-benefit-household-by-uin" or document.get("revision") != 1:
        raise ProofFailure("the SRO integration no longer has the expected blue revision")
    document["revision"] = 2
    integration.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def build_generation(registryctl: Path, source: Path, destination: Path) -> str:
    run(
        [
            str(registryctl),
            "build",
            "--project-dir",
            str(source),
            "--environment",
            "local",
        ]
    )
    private = source / ".registry-stack" / "build" / "local" / "private"
    relay = destination / "relay"
    notary = destination / "notary"
    shutil.copytree(private / "relay" / "config", relay)
    notary.mkdir(parents=True)
    shutil.copy2(private / "notary" / "config" / "notary.yaml", notary / "notary.yaml")
    document = yaml.safe_load((notary / "notary.yaml").read_text(encoding="utf-8"))
    return document["evidence"]["claims"][0]["evidence_mode"]["consultations"]["household"]["profile"]["contract_hash"]


def write_override(path: Path, generation: Path, *, relay: bool, notary: bool) -> None:
    services: dict[str, Any] = {}
    relay_mounts = [
        f"{generation / 'relay'}:/etc/registry-relay:ro",
    ]
    notary_mounts = [
        f"{generation / 'notary' / 'notary.yaml'}:/etc/registry-notary/notary.yaml:ro",
    ]
    if relay:
        services["sro-relay-state-bootstrap"] = {"volumes": relay_mounts}
        services["sro-social-relay"] = {"volumes": relay_mounts}
    if notary:
        services["sro-notary-state-install"] = {"volumes": notary_mounts}
        services["sro-notary"] = {"volumes": notary_mounts}
    path.write_text(yaml.safe_dump({"services": services}, sort_keys=False), encoding="utf-8")


def compose_command(project_name: str, override: Path | None = None) -> list[str]:
    command = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--env-file",
        str(ROOT / "versions.env"),
        "--env-file",
        str(ROOT / ".env"),
        "--file",
        str(ROOT / "compose.yaml"),
    ]
    if override is not None:
        command.extend(["--file", str(override)])
    return command


def wait_for_ready(url: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/ready", timeout=2) as response:
                if response.status in (200, 204):
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    raise ProofFailure("SRO Notary did not become ready")


def shared_notary_url(compose: Sequence[str], environment: Mapping[str, str]) -> str:
    result = run([*compose, "port", "sro-social-relay", "8081"], environment=environment)
    address = result.stdout.strip().splitlines()[-1]
    match = re.search(r":([0-9]+)$", address)
    if match is None:
        raise ProofFailure("could not resolve the SRO Notary port shared by its Relay container")
    return f"http://127.0.0.1:{match.group(1)}"


def evaluate(url: str, token: str, subject: str) -> dict[str, Any]:
    body = json.dumps(
        {
            "target": {
                "type": "Person",
                "identifiers": [{"scheme": "solmara_uin", "value": subject}],
            },
            "claims": [CLAIM_ID],
            "disclosure": "predicate",
            "format": RESULT_FORMAT,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/v1/evaluations",
        data=body,
        method="POST",
        headers={
            "Accept": RESULT_FORMAT,
            "Content-Type": "application/json",
            "Data-Purpose": PURPOSE,
            "x-api-key": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as error:
        error.read()
        raise ProofFailure(f"SRO evaluation returned HTTP {error.code}") from error
    if status != 200 or not successful_evaluation(payload, subject):
        raise ProofFailure("SRO evaluation did not return the expected minimized predicate")
    return payload


def successful_evaluation(payload: Any, subject: str) -> bool:
    if not isinstance(payload, dict) or subject in json.dumps(payload, sort_keys=True):
        return False
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        return False
    result = results[0]
    return (
        result.get("claim_id") == CLAIM_ID
        and result.get("disclosure") == "predicate"
        and (result.get("value") is True or result.get("satisfied") is True)
    )


def relay_activity_counts(compose: Sequence[str], environment: Mapping[str, str]) -> tuple[int, int]:
    sql = (
        "SELECT (SELECT count(*) FROM relay_state_private.consultation_completion_intent),"
        "(SELECT count(*) FROM relay_state_private.dispatch_permit WHERE dispatched_at IS NOT NULL);"
    )
    user = environment.get("SOLMARA_POSTGRES_USER", "solmara_registry")
    result = run(
        [
            *compose,
            "exec",
            "--no-TTY",
            "postgres",
            "psql",
            "--username",
            user,
            "--dbname",
            "solmara_relay_sro_consultation",
            "--tuples-only",
            "--no-align",
            "--command",
            sql,
        ],
        environment=environment,
    )
    match = re.fullmatch(r"\s*([0-9]+)\|([0-9]+)\s*", result.stdout)
    if match is None:
        raise ProofFailure("could not read the SRO Relay execution counters")
    return int(match.group(1)), int(match.group(2))


def sensitive_patterns(environment: Mapping[str, str]) -> dict[str, bytes]:
    patterns = {
        "blue synthetic subject": BLUE_SUBJECT.encode("utf-8"),
        "successor synthetic subject": GREEN_SUBJECT.encode("utf-8"),
    }
    for name, value in environment.items():
        if len(value) >= 16 and any(marker in name for marker in SENSITIVE_ENV_MARKERS):
            patterns[f"credential from {name}"] = value.encode("utf-8")
    return patterns


def scan_paths(paths: Sequence[Path], patterns: Mapping[str, bytes]) -> None:
    for root in paths:
        candidates = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in candidates:
            data = path.read_bytes()
            for description, pattern in patterns.items():
                if pattern in data:
                    raise ProofFailure(f"{description} appeared in captured artifact {path.name}")


def main() -> int:
    if not (ROOT / ".env").is_file():
        raise ProofFailure(".env is missing; run `just generate` first")
    environment = read_env(ROOT / "versions.env")
    environment.update(read_env(ROOT / ".env"))
    environment.update(os.environ)
    environment.update(
        {
            "SOLMARA_POSTGRES_PORT": "0",
            "SOLMARA_SRO_RELAY_PORT": "0",
            "SOLMARA_SRO_NOTARY_PORT": "0",
        }
    )
    token = environment.get("SRO_CHILD_BENEFIT_CLIENT_TOKEN", "")
    if not token:
        raise ProofFailure("generated SRO client credential is missing")

    registryctl_result = run([str(ROOT / "scripts" / "registryctl-pinned.sh"), "path"])
    registryctl = Path(registryctl_result.stdout.strip())
    project_name = f"solmara-contract-proof-{os.getpid()}"

    with tempfile.TemporaryDirectory(prefix="solmara-contract-proof-") as temporary:
        workspace = Path(temporary)
        blue_project = workspace / "projects" / "blue"
        green_project = workspace / "projects" / "green"
        shutil.copytree(PROJECT, blue_project)
        shutil.copytree(PROJECT, green_project)
        make_successor(green_project)

        print("contract-generation-proof: compiling blue and successor generations")
        blue = workspace / "generations" / "blue"
        green = workspace / "generations" / "green"
        blue_hash = build_generation(registryctl, blue_project, blue)
        green_hash = build_generation(registryctl, green_project, green)
        if blue_hash == green_hash:
            raise ProofFailure("the harmless successor did not move the consultation contract hash")

        blue_override = workspace / "blue.compose.yaml"
        mixed_override = workspace / "mixed.compose.yaml"
        green_override = workspace / "green.compose.yaml"
        write_override(blue_override, blue, relay=True, notary=True)
        write_override(mixed_override, green, relay=False, notary=True)
        write_override(green_override, green, relay=True, notary=True)
        blue_compose = compose_command(project_name, blue_override)
        mixed_compose = compose_command(project_name, mixed_override)
        green_compose = compose_command(project_name, green_override)
        evidence = workspace / "evidence"
        evidence.mkdir()

        try:
            print("contract-generation-proof: starting the complete blue generation")
            run(
                [*blue_compose, "up", "--detach", "--wait", "--wait-timeout", "180", "sro-notary"],
                environment=environment,
                timeout=300,
            )
            blue_url = shared_notary_url(blue_compose, environment)
            wait_for_ready(blue_url)
            blue_response = evaluate(blue_url, token, BLUE_SUBJECT)
            (evidence / "blue-response.json").write_text(
                json.dumps(blue_response, sort_keys=True), encoding="utf-8"
            )
            before_mixed = relay_activity_counts(blue_compose, environment)
            if before_mixed[0] < 1:
                raise ProofFailure("the blue generation did not execute its Relay consultation")

            print("contract-generation-proof: rejecting the mixed blue Relay / successor Notary")
            run([*blue_compose, "stop", "sro-notary"], environment=environment)
            run(
                [
                    *mixed_compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "sro-notary-state-install",
                ],
                environment=environment,
            )
            mixed_name = f"{project_name}-mixed-notary"
            try:
                mixed = run(
                    [
                        *mixed_compose,
                        "run",
                        "--rm",
                        "--no-deps",
                        "--name",
                        mixed_name,
                        "sro-notary",
                    ],
                    environment=environment,
                    timeout=45,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                run(["docker", "rm", "--force", mixed_name], check=False)
                raise ProofFailure("mixed-generation Notary unexpectedly kept serving") from error
            (evidence / "mixed-notary.log").write_text(mixed.stdout, encoding="utf-8")
            if mixed.returncode == 0:
                raise ProofFailure("mixed-generation Notary unexpectedly activated")
            expected_failure = "ERROR Relay consultation profile does not match its configured pin"
            if expected_failure not in mixed.stdout:
                raise ProofFailure("mixed-generation Notary failed for an unexpected reason")
            after_mixed = relay_activity_counts(blue_compose, environment)
            if after_mixed != before_mixed:
                raise ProofFailure("mixed-generation activation reached Relay execute or source dispatch")

            blue_logs = run([*blue_compose, "logs", "--no-color"], environment=environment)
            (evidence / "blue-services.log").write_text(blue_logs.stdout, encoding="utf-8")
            run([*blue_compose, "down", "--remove-orphans"], environment=environment)

            print("contract-generation-proof: activating the complete successor generation")
            run(
                [*green_compose, "up", "--detach", "--wait", "--wait-timeout", "180", "sro-notary"],
                environment=environment,
                timeout=300,
            )
            green_url = shared_notary_url(green_compose, environment)
            wait_for_ready(green_url)
            green_response = evaluate(green_url, token, GREEN_SUBJECT)
            (evidence / "green-response.json").write_text(
                json.dumps(green_response, sort_keys=True), encoding="utf-8"
            )
            after_green = relay_activity_counts(green_compose, environment)
            if after_green[0] <= after_mixed[0]:
                raise ProofFailure("the complete successor did not execute its Relay consultation")
            (evidence / "green-services.log").write_text(
                run([*green_compose, "logs", "--no-color"], environment=environment).stdout,
                encoding="utf-8",
            )

            scan_paths([blue, green, evidence], sensitive_patterns(environment))
        finally:
            preserve_cleanup_failure(
                lambda: run(
                    [*green_compose, "down", "--volumes", "--remove-orphans"],
                    environment=environment,
                    timeout=120,
                    check=False,
                ),
                environment=environment,
                primary_failure_active=sys.exc_info()[0] is not None,
            )

    print("contract-generation-proof: blue success, mixed rejection, and successor success passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProofFailure as error:
        print(f"contract-generation-proof: {error}", file=sys.stderr)
        raise SystemExit(1) from error
