#!/usr/bin/env python3
"""Prove Solmara's live Relay and immutable-extract cadences over HTTP.

The proof deliberately emits only named checks. Selectors, tokens, signed JWS
bytes, source values, extract names, and private operational data stay inside
the process and are never copied into its result or errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "generator") not in sys.path:
    sys.path.insert(0, str(ROOT / "generator"))

from scenarios import common as evidence_common  # noqa: E402
from scenarios.service_config import requirement_config, service_url  # noqa: E402
from solmara_lab import publisher  # noqa: E402

MOSD_SERVICE = "mosd-programme-evidence"
MOSD_RELAY_SERVICE = "mosd-relay"
SRO_SERVICE = "sro-evidence"
NON_SRO_SERVICES = (
    "cra-relay",
    "nia-relay",
    MOSD_RELAY_SERVICE,
    "sipf-relay",
    "nagdi-relay",
    "mint",
    "cra-evidence",
    "nia-evidence",
    MOSD_SERVICE,
    "sipf-evidence",
    "nagdi-evidence",
)
TOPOLOGY_SERVICES = (*NON_SRO_SERVICES, SRO_SERVICE)
MOSD_REQUIREMENT = "programme-child-benefit"
SRO_REQUIREMENT = "sro-child-benefit"
MOSD_CONTROL_SUBJECT = "2300010248"
SRO_CONTROL_SUBJECT = "2300010248"
MOSD_CONCEPT = "not-already-enrolled"
SRO_CONCEPT = "household-below-poverty-threshold"
MOSD_PUBLISHER_SERVICE = "mosd-source-publisher"
MOSD_SOURCE_VOLUME = "mosd-relay-source"
RELAY_SOURCE_DESTINATION = "/var/lib/relay/source"
SRO_RUNTIME = Path("runtime/evidence-cells/cells/sro/runtime.yaml")
SRO_PROFILE = "sro-poverty-extract"
SRO_CONTAINER_DIRECTORY = PurePosixPath("/var/lib/registry-evidence/sro/extracts")
READINESS_ATTEMPTS = 45
READINESS_INTERVAL_SECONDS = 1.0
REFUSAL_OBSERVATION_SECONDS = 8.0

_PUBLIC_ERROR = "lifecycle proof did not complete"
_FORBIDDEN_OUTPUT_PATTERNS = (
    re.compile(r"\b(?:uin|selector|token|authorization|jws|signature|payload)\b", re.I),
    re.compile(r"\b(?:poverty_band|duplicate_flag|record_revision|source row)\b", re.I),
    re.compile(r"\b(?:\.sqlite|runtime\.yaml|/var/lib/)\b", re.I),
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
)


class LifecycleProofError(RuntimeError):
    """A value-free lifecycle proof failure."""


class Operations(Protocol):
    def load_environment(self) -> None: ...

    def validate_preconditions(self) -> None: ...

    def observe_evidence(self, requirement: str) -> bool: ...

    def generation(self, service: str) -> str: ...

    def capture_mosd_fixture(self) -> "MosdFixture": ...

    def mutate_mosd(self, duplicate: bool) -> None: ...

    def restore_mosd_fixture(self, fixture: "MosdFixture") -> None: ...

    def capture_sro_binding(self) -> bytes: ...

    def publish_changed_sro(self) -> "ExtractPublication": ...

    def bind_sro(self, publication: "ExtractPublication") -> None: ...

    def restart_sro(self) -> None: ...

    def wait_sro_ready(self) -> None: ...

    def prove_replacement_refusals(self) -> None: ...

    def restore_sro_binding(self, original: bytes) -> None: ...

    def discard_sro_publication(self, publication: "ExtractPublication") -> None: ...


@dataclass(frozen=True)
class ExtractPublication:
    path: Path
    container_path: str
    extract_id: str


@dataclass(frozen=True)
class MosdFixture:
    publisher_backup_started: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _run_command(
    command: Sequence[str], *, cwd: Path = ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


def _compose_command(*arguments: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        "versions.env",
        "--env-file",
        ".env",
        "-f",
        "compose.yaml",
        *arguments,
    ]


def _safe_failure(error: BaseException) -> LifecycleProofError:
    return LifecycleProofError(_PUBLIC_ERROR)


def _claim_value(result: evidence_common.StepHttpResult, concept: str) -> bool:
    body = result.body if isinstance(result.body, dict) else {}
    values = {
        member.get("claim_id"): member.get("value")
        for member in body.get("results", [])
        if isinstance(member, dict)
    }
    value = values.get(concept)
    if not isinstance(value, bool):
        raise LifecycleProofError(_PUBLIC_ERROR)
    return value


def _verify_signed_observation(*, service_id: str, subject: str, purpose: str) -> bool:
    token = evidence_common.evidence_access_token()
    if not token:
        raise LifecycleProofError(_PUBLIC_ERROR)
    config = requirement_config(service_id)
    request = evidence_common.evidence_body(
        subject,
        str(config["requirement"]),
        purpose,
    )
    response = evidence_common.http_json(
        "POST",
        service_url(service_id),
        evidence_common.evidence_headers(token),
        request,
        timeout=10.0,
    )
    verified = evidence_common.normalized_evidence_result(
        response,
        request=request,
        service_id=service_id,
    )
    if verified.status != 200:
        raise LifecycleProofError(_PUBLIC_ERROR)
    concept = MOSD_CONCEPT if service_id == MOSD_REQUIREMENT else SRO_CONCEPT
    return _claim_value(verified, concept)


def _load_sro_binding(path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        extracts = document["sourceExtracts"]
        if set(extracts) != {SRO_PROFILE}:
            raise ValueError
        binding = extracts[SRO_PROFILE]
        if set(binding) != {"path"} or not isinstance(binding["path"], str):
            raise ValueError
        container_path = PurePosixPath(binding["path"])
        if (
            container_path.parent != SRO_CONTAINER_DIRECTORY
            or not container_path.name.startswith("sro-poverty-")
            or container_path.suffix != ".sqlite"
        ):
            raise ValueError
        return document, binding["path"], container_path.stem
    except (KeyError, OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError):
        raise LifecycleProofError(_PUBLIC_ERROR) from None


def _replace_runtime_binding(path: Path, container_path: str) -> None:
    _, old_container_path, _ = _load_sro_binding(path)
    new_path = PurePosixPath(container_path)
    if (
        new_path.parent != SRO_CONTAINER_DIRECTORY
        or not new_path.name.startswith("sro-poverty-")
        or new_path.suffix != ".sqlite"
    ):
        raise LifecycleProofError(_PUBLIC_ERROR)
    original = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?<![^\s{{]){re.escape(old_container_path)}(?=[\s}}])")
    rendered, replacements = pattern.subn(container_path, original)
    if replacements != 1:
        raise LifecycleProofError(_PUBLIC_ERROR)
    _replace_file(path, rendered.encode("utf-8"))


def _replace_file(path: Path, content: bytes) -> None:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    directory_mode = stat.S_IMODE(path.parent.stat().st_mode)
    path.parent.chmod(directory_mode | stat.S_IWUSR)
    temporary = path.with_name(f".{path.name}.lifecycle-{os.getpid()}.tmp")
    try:
        if temporary.exists():
            temporary.unlink()
        temporary.write_bytes(content)
        temporary.chmod(original_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
        path.parent.chmod(directory_mode)


def _publish_changed_sro(root: Path) -> ExtractPublication:
    published_at = _timestamp(_now())
    extract_id = publisher.timestamped_extract_id("sro", published_at)
    target = publisher.extract_path(root, extract_id)
    if target.exists() or target.is_symlink():
        raise LifecycleProofError(_PUBLIC_ERROR)
    staging_parent = root / "runtime"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".lifecycle-sro-", dir=staging_parent
    ) as temporary:
        staged = publisher.publish_extract(
            Path(temporary), "sro", published_at, extract_id
        )
        original_mode = stat.S_IMODE(staged.stat().st_mode)
        try:
            staged.chmod(original_mode | stat.S_IWUSR)
            with sqlite3.connect(staged) as connection:
                row = connection.execute(
                    """
                    SELECT record_id, lifecycle_state, recorded_at
                    FROM poverty_evidence
                    WHERE uin = ?
                    """,
                    (SRO_CONTROL_SUBJECT,),
                ).fetchone()
                if row is None:
                    raise LifecycleProofError(_PUBLIC_ERROR)
                changed = "standard"
                revision_input = {
                    "record_id": str(row[0]),
                    "lifecycle_state": str(row[1]),
                    "recorded_at": str(row[2]),
                    "uin": SRO_CONTROL_SUBJECT,
                    "poverty_band": changed,
                }
                revision = (
                    "rev-"
                    + hashlib.sha256(
                        json.dumps(
                            revision_input, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest()[:16]
                )
                connection.execute(
                    """
                    UPDATE poverty_evidence
                    SET poverty_band = ?, record_revision = ?
                    WHERE uin = ?
                    """,
                    (changed, revision, SRO_CONTROL_SUBJECT),
                )
                connection.commit()
                connection.execute("VACUUM")
        finally:
            staged.chmod(0o444)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(staged, target)
        except FileExistsError:
            raise LifecycleProofError(_PUBLIC_ERROR) from None
    try:
        publisher.validate_extract(
            target,
            "sro",
            observed_at=published_at,
            expected_extract_id=extract_id,
            expected_published_at=published_at,
        )
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return ExtractPublication(
        target,
        str(SRO_CONTAINER_DIRECTORY / target.name),
        extract_id,
    )


def _publish_invalid_sro(root: Path, *, stale: bool) -> Path:
    published_at = _timestamp(_now() - (timedelta(days=2) if stale else timedelta()))
    suffix = "stale" if stale else "invalid"
    base_id = publisher.timestamped_extract_id("sro", published_at)
    extract_id = f"{base_id}-{suffix}-{os.getpid()}"
    path = publisher.publish_extract(root, "sro", published_at, extract_id)
    if not stale:
        original_mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(original_mode | stat.S_IWUSR)
        try:
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE evidence_extract SET published_at = ?", ("invalid",)
                )
                connection.commit()
        except BaseException:
            path.chmod(0o444)
            path.unlink(missing_ok=True)
            raise
        finally:
            if path.exists():
                path.chmod(0o444)
    return path


class LocalOperations:
    """Real local runtime operations, with all sensitive values kept internal."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root.resolve()
        self.sro_runtime = self.root / SRO_RUNTIME

    def load_environment(self) -> None:
        _load_dotenv(self.root / ".env")
        os.environ.pop("SOLMARA_EVIDENCE_ACCESS_TOKEN", None)
        os.environ["SOLMARA_MINT_URL"] = "https://localhost:4341"
        os.environ["SOLMARA_MINT_ASSERTION_AUDIENCE"] = (
            "https://mint.solmara.registrystack.org/token"
        )
        os.environ["SOLMARA_EVIDENCE_CLIENT_ID"] = "solmara-demo"
        os.environ["SOLMARA_EVIDENCE_CLIENT_KEY"] = str(
            self.root
            / "config/evidence/local/cells/mint/clients/solmara-demo-client-key"
        )
        os.environ["SOLMARA_EVIDENCE_CA_BUNDLE"] = str(
            self.root / "config/evidence/local/tls/ca.crt"
        )
        os.environ["SOLMARA_SRO_EVIDENCE_URL"] = "https://localhost:4341/evidence/sro"
        os.environ["SOLMARA_MOSD_PROGRAMME_EVIDENCE_URL"] = (
            "https://localhost:4341/evidence/mosd-programme"
        )
        os.environ["SOLMARA_EVIDENCE_AUDIENCE"] = evidence_common.EVIDENCE_AUDIENCE
        evidence_common._TOKEN_CACHE = ("", 0.0)
        evidence_common._JWKS_CACHE.clear()

    def validate_preconditions(self) -> None:
        required_files = (
            self.sro_runtime,
            self.root / "scripts/local-relay-source-publisher.py",
            Path(os.environ["SOLMARA_EVIDENCE_CLIENT_KEY"]),
            Path(os.environ["SOLMARA_EVIDENCE_CA_BUNDLE"]),
        )
        if not all(path.is_file() for path in required_files):
            raise LifecycleProofError(_PUBLIC_ERROR)
        _, _, bound_id = _load_sro_binding(self.sro_runtime)
        bound = publisher.extract_path(self.root, bound_id)
        publisher.validate_extract(
            bound,
            "sro",
            observed_at=_timestamp(_now()),
            expected_extract_id=bound_id,
        )
        for service in TOPOLOGY_SERVICES:
            self.generation(service)
        self._require_read_only_named_volume(
            MOSD_RELAY_SERVICE,
            MOSD_SOURCE_VOLUME,
            RELAY_SOURCE_DESTINATION,
        )
        self._require_bind_mount(SRO_SERVICE, self.sro_runtime.parent)
        self._require_bind_mount(SRO_SERVICE, self.root / publisher.EVIDENCE_DIRECTORY)

    def _require_bind_mount(self, service: str, expected: Path) -> None:
        completed = _run_command(_compose_command("ps", "-q", service))
        container_id = completed.stdout.strip()
        if not container_id:
            raise LifecycleProofError(_PUBLIC_ERROR)
        inspection = _run_command(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id]
        )
        try:
            mounts = json.loads(inspection.stdout)
            if not isinstance(mounts, list):
                raise ValueError
            matched = any(
                isinstance(mount, dict)
                and mount.get("Type") == "bind"
                and isinstance(mount.get("Source"), str)
                and Path(mount["Source"]).exists()
                and os.path.samefile(mount["Source"], expected)
                for mount in mounts
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            raise LifecycleProofError(_PUBLIC_ERROR) from None
        if not matched:
            raise LifecycleProofError(_PUBLIC_ERROR)

    def _require_read_only_named_volume(
        self, service: str, volume: str, destination: str
    ) -> None:
        completed = _run_command(_compose_command("ps", "-q", service))
        container_id = completed.stdout.strip()
        if not container_id:
            raise LifecycleProofError(_PUBLIC_ERROR)
        inspection = _run_command(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id]
        )
        project = os.environ.get("COMPOSE_PROJECT_NAME", "")
        expected_name = f"{project}_{volume}" if project else ""
        try:
            mounts = json.loads(inspection.stdout)
            if not isinstance(mounts, list):
                raise ValueError
            matched = any(
                isinstance(mount, dict)
                and mount.get("Type") == "volume"
                and mount.get("Destination") == destination
                and mount.get("RW") is False
                and isinstance(mount.get("Name"), str)
                and (
                    mount["Name"] == expected_name
                    if expected_name
                    else mount["Name"].endswith(f"_{volume}")
                )
                for mount in mounts
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise LifecycleProofError(_PUBLIC_ERROR) from None
        if not matched:
            raise LifecycleProofError(_PUBLIC_ERROR)

    def observe_evidence(self, requirement: str) -> bool:
        purpose = (
            evidence_common.PURPOSES["child_benefit"]
            if requirement in {MOSD_REQUIREMENT, SRO_REQUIREMENT}
            else ""
        )
        subject = (
            MOSD_CONTROL_SUBJECT
            if requirement == MOSD_REQUIREMENT
            else SRO_CONTROL_SUBJECT
        )
        return _verify_signed_observation(
            service_id=requirement,
            subject=subject,
            purpose=purpose,
        )

    def generation(self, service: str) -> str:
        completed = _run_command(_compose_command("ps", "--format", "json", service))
        try:
            parsed = json.loads(completed.stdout)
            documents = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            documents = [
                json.loads(line)
                for line in completed.stdout.splitlines()
                if line.strip()
            ]
        if len(documents) != 1:
            raise LifecycleProofError(_PUBLIC_ERROR)
        document = documents[0]
        container_id = document.get("ID")
        state = document.get("State")
        if not isinstance(container_id, str) or not container_id or state != "running":
            raise LifecycleProofError(_PUBLIC_ERROR)
        inspection = _run_command(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Id}} {{.State.StartedAt}} {{.RestartCount}}",
                container_id,
            ]
        ).stdout.strip()
        if not inspection:
            raise LifecycleProofError(_PUBLIC_ERROR)
        return inspection

    def capture_mosd_fixture(self) -> MosdFixture:
        try:
            self._run_mosd_publisher("begin-proof")
        except BaseException:
            try:
                self._run_mosd_publisher("restore-proof")
            except BaseException:
                pass
            raise LifecycleProofError(_PUBLIC_ERROR) from None
        return MosdFixture(publisher_backup_started=True)

    def mutate_mosd(self, duplicate: bool) -> None:
        if duplicate is not True:
            raise LifecycleProofError(_PUBLIC_ERROR)
        self._run_mosd_publisher("set-proof-state")

    def restore_mosd_fixture(self, fixture: MosdFixture) -> None:
        if fixture.publisher_backup_started is not True:
            raise LifecycleProofError(_PUBLIC_ERROR)
        self._run_mosd_publisher("restore-proof")

    def _run_mosd_publisher(self, verb: str) -> None:
        if verb not in {"begin-proof", "set-proof-state", "restore-proof"}:
            raise LifecycleProofError(_PUBLIC_ERROR)
        _run_command(
            _compose_command(
                "run",
                "--rm",
                "-T",
                "--no-deps",
                MOSD_PUBLISHER_SERVICE,
                verb,
            )
        )

    def capture_sro_binding(self) -> bytes:
        _load_sro_binding(self.sro_runtime)
        return self.sro_runtime.read_bytes()

    def publish_changed_sro(self) -> ExtractPublication:
        return _publish_changed_sro(self.root)

    def bind_sro(self, publication: ExtractPublication) -> None:
        _replace_runtime_binding(self.sro_runtime, publication.container_path)

    def restart_sro(self) -> None:
        _run_command(_compose_command("restart", "--no-deps", SRO_SERVICE))

    def wait_sro_ready(self) -> None:
        last_error: BaseException | None = None
        for _ in range(READINESS_ATTEMPTS):
            try:
                result = evidence_common.http_json(
                    "GET",
                    service_url(SRO_REQUIREMENT, "/ready"),
                    {},
                    timeout=2.0,
                )
                if result.status in {200, 204}:
                    return
            except BaseException as error:
                last_error = error
            time.sleep(READINESS_INTERVAL_SECONDS)
        raise _safe_failure(last_error or LifecycleProofError(_PUBLIC_ERROR))

    def _wait_sro_refused(self) -> None:
        deadline = time.monotonic() + REFUSAL_OBSERVATION_SECONDS
        while time.monotonic() < deadline:
            # Readiness describes process health, so it may remain healthy when
            # a bound extract is refused. Once ready, require the signed public
            # operation itself to fail; otherwise the bounded absence of
            # readiness is the fail-closed path.
            try:
                result = evidence_common.http_json(
                    "GET",
                    service_url(SRO_REQUIREMENT, "/ready"),
                    {},
                    timeout=1.0,
                )
                if result.status in {200, 204}:
                    break
            except BaseException:
                pass
            time.sleep(0.5)
        try:
            self.observe_evidence(SRO_REQUIREMENT)
        except LifecycleProofError:
            return
        raise LifecycleProofError(_PUBLIC_ERROR)

    def prove_replacement_refusals(self) -> None:
        active_document, _, active_id = _load_sro_binding(self.sro_runtime)
        active_runtime = self.sro_runtime.read_bytes()
        active = publisher.extract_path(self.root, active_id)
        before = active.read_bytes()
        try:
            publisher.publish_extract(
                self.root,
                "sro",
                _timestamp(_now()),
                active_id,
            )
        except FileExistsError:
            pass
        else:
            raise LifecycleProofError(_PUBLIC_ERROR)
        if active.read_bytes() != before:
            raise LifecycleProofError(_PUBLIC_ERROR)
        if not isinstance(active_document, dict):
            raise LifecycleProofError(_PUBLIC_ERROR)

        invalid_paths: list[Path] = []
        try:
            for stale in (True, False):
                candidate = _publish_invalid_sro(self.root, stale=stale)
                invalid_paths.append(candidate)
                _replace_runtime_binding(
                    self.sro_runtime,
                    str(SRO_CONTAINER_DIRECTORY / candidate.name),
                )
                self.restart_sro()
                self._wait_sro_refused()
                _replace_file(self.sro_runtime, active_runtime)
                self.restart_sro()
                self.wait_sro_ready()
        finally:
            _replace_file(self.sro_runtime, active_runtime)
            try:
                self.restart_sro()
                self.wait_sro_ready()
            except BaseException:
                pass
            for candidate in invalid_paths:
                candidate.unlink(missing_ok=True)

    def restore_sro_binding(self, original: bytes) -> None:
        _replace_file(self.sro_runtime, original)

    def discard_sro_publication(self, publication: ExtractPublication) -> None:
        _, _, active_id = _load_sro_binding(self.sro_runtime)
        if active_id == publication.extract_id:
            raise LifecycleProofError(_PUBLIC_ERROR)
        publication.path.unlink(missing_ok=True)


def run_proof(operations: Operations | None = None) -> dict[str, Any]:
    """Run the live proof and return a deliberately value-free result."""

    operations = operations or LocalOperations()
    checks: dict[str, bool] = {
        "signed-http-observations": False,
        "relay-live-change-without-restart": False,
        "extract-stays-bound-until-restart": False,
        "sro-only-restart-activates-publication": False,
        "replacement-failures-close": False,
        "deterministic-state-restored": False,
    }
    original_binding: bytes | None = None
    initial_generations: dict[str, str] = {}
    published: ExtractPublication | None = None
    mosd_fixture: MosdFixture | None = None
    sro_may_need_restore = False
    primary_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        operations.load_environment()
        operations.validate_preconditions()
        initial_generations = {
            service: operations.generation(service) for service in TOPOLOGY_SERVICES
        }
        mosd_fixture = operations.capture_mosd_fixture()
        original_binding = operations.capture_sro_binding()

        mosd_before = operations.observe_evidence(MOSD_REQUIREMENT)
        sro_before = operations.observe_evidence(SRO_REQUIREMENT)
        if mosd_before is not True or sro_before is not True:
            raise LifecycleProofError(_PUBLIC_ERROR)
        checks["signed-http-observations"] = True

        operations.mutate_mosd(True)
        mosd_after = operations.observe_evidence(MOSD_REQUIREMENT)
        if mosd_after is not False:
            raise LifecycleProofError(_PUBLIC_ERROR)
        for service in (MOSD_RELAY_SERVICE, MOSD_SERVICE):
            if operations.generation(service) != initial_generations[service]:
                raise LifecycleProofError(_PUBLIC_ERROR)
        checks["relay-live-change-without-restart"] = True

        published = operations.publish_changed_sro()
        if operations.observe_evidence(SRO_REQUIREMENT) is not sro_before:
            raise LifecycleProofError(_PUBLIC_ERROR)

        sro_may_need_restore = True
        operations.bind_sro(published)
        if operations.observe_evidence(SRO_REQUIREMENT) is not sro_before:
            raise LifecycleProofError(_PUBLIC_ERROR)
        checks["extract-stays-bound-until-restart"] = True

        operations.restart_sro()
        operations.wait_sro_ready()
        if operations.observe_evidence(SRO_REQUIREMENT) is not False:
            raise LifecycleProofError(_PUBLIC_ERROR)
        for service in NON_SRO_SERVICES:
            if operations.generation(service) != initial_generations[service]:
                raise LifecycleProofError(_PUBLIC_ERROR)
        if operations.generation(SRO_SERVICE) == initial_generations[SRO_SERVICE]:
            raise LifecycleProofError(_PUBLIC_ERROR)
        checks["sro-only-restart-activates-publication"] = True

        operations.prove_replacement_refusals()
        for service in NON_SRO_SERVICES:
            if operations.generation(service) != initial_generations[service]:
                raise LifecycleProofError(_PUBLIC_ERROR)
        checks["replacement-failures-close"] = True
    except BaseException as error:
        primary_error = error
    finally:
        cleanup_errors: list[BaseException] = []
        if mosd_fixture is not None:
            try:
                operations.restore_mosd_fixture(mosd_fixture)
            except BaseException as error:
                cleanup_errors.append(error)
        sro_restored = original_binding is None
        if original_binding is not None:
            try:
                operations.restore_sro_binding(original_binding)
                if sro_may_need_restore:
                    operations.restart_sro()
                    operations.wait_sro_ready()
                sro_restored = True
            except BaseException as error:
                cleanup_errors.append(error)
        if published is not None and sro_restored:
            try:
                operations.discard_sro_publication(published)
            except BaseException as error:
                cleanup_errors.append(error)
        if primary_error is None and not cleanup_errors:
            try:
                if operations.observe_evidence(MOSD_REQUIREMENT) is not True:
                    raise LifecycleProofError(_PUBLIC_ERROR)
                if operations.observe_evidence(SRO_REQUIREMENT) is not True:
                    raise LifecycleProofError(_PUBLIC_ERROR)
                for service in NON_SRO_SERVICES:
                    if operations.generation(service) != initial_generations[service]:
                        raise LifecycleProofError(_PUBLIC_ERROR)
                checks["deterministic-state-restored"] = True
            except BaseException as error:
                cleanup_errors.append(error)
        if cleanup_errors:
            cleanup_error = cleanup_errors[0]

    if primary_error is not None or cleanup_error is not None:
        raise _safe_failure(
            cleanup_error or primary_error or LifecycleProofError(_PUBLIC_ERROR)
        )
    if not all(checks.values()):
        raise LifecycleProofError(_PUBLIC_ERROR)
    return {"status": "pass", "proof": "live-http", "checks": checks}


def _assert_sanitized(value: str) -> None:
    for pattern in _FORBIDDEN_OUTPUT_PATTERNS:
        if pattern.search(value):
            raise LifecycleProofError("proof output violated its redaction contract")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove Relay-live and immutable-extract Evidence lifecycles"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_proof()
        rendered = json.dumps(result, sort_keys=True)
        _assert_sanitized(rendered)
        if args.json:
            print(rendered)
        else:
            print("live-lifecycle-proof: pass")
        return 0
    except BaseException:
        print("live-lifecycle-proof: failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
