#!/usr/bin/env python3
"""Prove that local Notary PostgreSQL correctness state survives replacement.

This is deliberately a Solmara-local PostgreSQL 16 gate. It exercises the
operator-facing ``just down`` / ``just up`` path, verifies that PostgreSQL uses
the checkout's named data volume, and compares every Notary correctness-state
table before any post-restart doctor or scenario request can create new state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_POSTGRES_MAJOR = 16
EXPECTED_PGDATA = PurePosixPath("/var/lib/postgresql/data")
DEFAULT_WAIT_SECONDS = 300.0

AUTHORITIES = (
    ("cra", "cra-notary"),
    ("nia", "nia-notary"),
    ("sro", "sro-notary"),
    ("programme", "programme-notary"),
    ("sipf", "sipf-notary"),
    ("nagdi", "nagdi-notary"),
)

CORRECTNESS_TABLES = (
    "replay_identifier",
    "consumable_nonce",
    "evaluation",
    "batch_idempotency",
    "credential_status",
    "machine_quota",
    "subject_access_quota",
    "preauthorization_login_state",
    "preauthorization_tx_code",
)


class GateError(RuntimeError):
    """The restart-persistence proof could not be completed safely."""


class CommandError(GateError):
    """One bounded external command failed."""


class CommandRunner:
    """Injectable command and clock boundary used by the production gate."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> str:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            if len(detail) > 4_000:
                detail = detail[-4_000:]
            rendered = " ".join(command)
            suffix = f": {detail}" if detail else ""
            raise CommandError(
                f"command failed with exit {completed.returncode}: {rendered}{suffix}"
            )
        return completed.stdout

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class StateSnapshot:
    container_id: str
    system_identifier: str
    server_version_num: int
    data_directory: str
    volume_name: str
    counts: tuple[tuple[str, str, int], ...]

    def totals(self) -> dict[str, int]:
        totals = {authority: 0 for authority, _service in AUTHORITIES}
        for authority, _table, count in self.counts:
            totals[authority] += count
        return totals


def _is_postgres_storage_path(path: PurePosixPath) -> bool:
    """Return true when a mount can cover, replace, or subdivide PGDATA."""

    return (
        path == EXPECTED_PGDATA
        or path in EXPECTED_PGDATA.parents
        or EXPECTED_PGDATA in path.parents
    )


def validate_compose_pgdata_layout(config: object) -> str:
    """Return the resolved named volume after validating the PG16 layout."""

    if not isinstance(config, dict):
        raise GateError("Compose configuration is not an object")
    services = config.get("services")
    volumes = config.get("volumes")
    if not isinstance(services, dict) or not isinstance(volumes, dict):
        raise GateError("Compose configuration is missing services or volumes")
    postgres = services.get("postgres")
    declared = volumes.get("postgres-data")
    if not isinstance(postgres, dict) or not isinstance(declared, dict):
        raise GateError("Compose must declare postgres and postgres-data")
    resolved_name = declared.get("name")
    if not isinstance(resolved_name, str) or not resolved_name:
        raise GateError("Compose did not resolve the postgres-data volume name")

    configured = postgres.get("volumes")
    if not isinstance(configured, list):
        raise GateError("PostgreSQL has no configured volumes")
    postgres_storage = []
    for mount in configured:
        if not isinstance(mount, dict):
            raise GateError("PostgreSQL volume configuration is not normalized")
        target = mount.get("target")
        if isinstance(target, str) and _is_postgres_storage_path(PurePosixPath(target)):
            postgres_storage.append(mount)
    expected = [
        mount
        for mount in postgres_storage
        if mount.get("type") == "volume"
        and mount.get("source") == "postgres-data"
        and mount.get("target") == str(EXPECTED_PGDATA)
        and not mount.get("read_only", False)
    ]
    if len(postgres_storage) != 1 or len(expected) != 1:
        raise GateError(
            "PostgreSQL 16 must mount only named postgres-data directly and "
            "read-write at /var/lib/postgresql/data"
        )
    return resolved_name


def validate_runtime_pgdata_mounts(
    mounts: object,
    *,
    expected_volume: str,
    volume_labels: object,
    compose_project_name: str,
) -> None:
    """Reject anonymous, parent, nested, bind, and read-only PGDATA mounts."""

    if not isinstance(mounts, list):
        raise GateError("Docker did not return PostgreSQL mounts")
    storage_mounts = []
    for mount in mounts:
        if not isinstance(mount, dict):
            raise GateError("Docker returned a malformed PostgreSQL mount")
        destination = mount.get("Destination")
        if isinstance(destination, str) and _is_postgres_storage_path(
            PurePosixPath(destination)
        ):
            storage_mounts.append(mount)
    if len(storage_mounts) != 1:
        raise GateError(
            "PostgreSQL has an anonymous, parent, or nested volume overlapping PGDATA"
        )
    mount = storage_mounts[0]
    if (
        mount.get("Type") != "volume"
        or mount.get("Name") != expected_volume
        or mount.get("Destination") != str(EXPECTED_PGDATA)
        or mount.get("RW") is not True
    ):
        raise GateError(
            "PostgreSQL PGDATA is not the expected writable named postgres-data volume"
        )
    if not isinstance(volume_labels, dict):
        raise GateError("PostgreSQL named volume has no Compose ownership labels")
    if (
        volume_labels.get("com.docker.compose.project") != compose_project_name
        or volume_labels.get("com.docker.compose.volume") != "postgres-data"
    ):
        raise GateError(
            "PostgreSQL PGDATA volume is anonymous or belongs to another Compose project"
        )


def parse_control_snapshot(output: str) -> tuple[str, int, str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 3:
        raise GateError("PostgreSQL control query did not return exactly three values")
    system_identifier, version_text, data_directory = lines
    if not system_identifier.isdecimal() or int(system_identifier) <= 0:
        raise GateError("PostgreSQL returned an invalid system identifier")
    if not version_text.isdecimal():
        raise GateError("PostgreSQL returned an invalid server_version_num")
    server_version_num = int(version_text)
    if server_version_num // 10_000 != EXPECTED_POSTGRES_MAJOR:
        raise GateError(
            "the local restart gate is deliberately pinned to PostgreSQL 16; "
            "follow the documented major-upgrade procedure"
        )
    if data_directory != str(EXPECTED_PGDATA):
        raise GateError(
            f"PostgreSQL data_directory is {data_directory!r}, expected "
            f"{str(EXPECTED_PGDATA)!r}"
        )
    return system_identifier, server_version_num, data_directory


def parse_authority_counts(authority: str, output: str) -> dict[str, int]:
    expected = set(CORRECTNESS_TABLES)
    parsed: dict[str, int] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split("|")
        if len(parts) != 2:
            raise GateError(f"{authority} returned a malformed correctness-state row")
        table, count_text = parts
        if table not in expected or table in parsed or not count_text.isdecimal():
            raise GateError(f"{authority} returned invalid or duplicate table counts")
        parsed[table] = int(count_text)
    if set(parsed) != expected:
        missing = sorted(expected - set(parsed))
        raise GateError(
            f"{authority} correctness-state snapshot is incomplete: {', '.join(missing)}"
        )
    if sum(parsed.values()) == 0:
        raise GateError(
            f"{authority} has no correctness rows; run live smoke before the restart gate"
        )
    return parsed


def compare_snapshots(before: StateSnapshot, after: StateSnapshot) -> None:
    if before.container_id == after.container_id:
        raise GateError("just down/up reused the PostgreSQL container")
    if before.system_identifier != after.system_identifier:
        raise GateError(
            "PostgreSQL system_identifier changed across just down/up; "
            "the named cluster was not preserved"
        )
    if before.server_version_num != after.server_version_num:
        raise GateError("PostgreSQL server_version_num changed across restart")
    if before.data_directory != after.data_directory:
        raise GateError("PostgreSQL data_directory changed across restart")
    if before.volume_name != after.volume_name:
        raise GateError("PostgreSQL named volume changed across restart")
    if before.counts != after.counts:
        before_map = {(a, t): c for a, t, c in before.counts}
        after_map = {(a, t): c for a, t, c in after.counts}
        changes = [
            f"{authority}.{table}: {before_map.get((authority, table))} -> "
            f"{after_map.get((authority, table))}"
            for authority, table in sorted(set(before_map) | set(after_map))
            if before_map.get((authority, table)) != after_map.get((authority, table))
        ]
        raise GateError(
            "Notary correctness-state counts changed across restart: " + "; ".join(changes)
        )


class RestartPersistenceGate:
    def __init__(
        self,
        *,
        root: Path = ROOT,
        runner: CommandRunner | None = None,
        environ: Mapping[str, str] | None = None,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
    ) -> None:
        self.root = root.resolve()
        self.runner = runner or CommandRunner()
        self.env = dict(os.environ if environ is None else environ)
        self.wait_seconds = wait_seconds
        self.compose_project_name = ""
        self.compose: list[str] = []
        self.expected_volume = ""

    def _run(self, command: Sequence[str]) -> str:
        return self.runner.run(command, cwd=self.root, env=self.env)

    def resolve_compose(self) -> None:
        for required in (".env", "versions.env", "compose.yaml"):
            if not (self.root / required).is_file():
                raise GateError(f"{required} is missing")
        project = self.env.get("COMPOSE_PROJECT_NAME", "").strip()
        if not project:
            project = self._run(
                [sys.executable, str(self.root / "scripts" / "compose_project_name.py")]
            ).strip()
        if not project:
            raise GateError("could not resolve COMPOSE_PROJECT_NAME")
        self.compose_project_name = project
        self.env["COMPOSE_PROJECT_NAME"] = project
        self.compose = [
            "docker",
            "compose",
            "--env-file",
            str(self.root / "versions.env"),
            "--env-file",
            str(self.root / ".env"),
            "-f",
            str(self.root / "compose.yaml"),
        ]
        rendered = self._run([*self.compose, "config", "--format", "json"])
        try:
            config = json.loads(rendered)
        except json.JSONDecodeError as error:
            raise GateError("Docker Compose returned invalid configuration JSON") from error
        self.expected_volume = validate_compose_pgdata_layout(config)

    def _compose(self, *arguments: str) -> str:
        if not self.compose:
            raise GateError("Compose has not been resolved")
        return self._run([*self.compose, *arguments])

    def service_container_id(self, service: str, *, include_stopped: bool = False) -> str:
        arguments = ["ps", "-q"]
        if include_stopped:
            arguments.append("--all")
        arguments.append(service)
        output = self._compose(*arguments).strip()
        identifiers = [line for line in output.splitlines() if line]
        if len(identifiers) > 1:
            raise GateError(f"Compose returned multiple containers for {service}")
        return identifiers[0] if identifiers else ""

    def _container_health(self, container_id: str) -> str:
        return self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container_id,
            ]
        ).strip()

    def _installer_status(self, container_id: str) -> tuple[str, int]:
        output = self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}|{{.State.ExitCode}}",
                container_id,
            ]
        ).strip()
        parts = output.split("|")
        if len(parts) != 2 or not parts[1].lstrip("-").isdecimal():
            raise GateError("Docker returned a malformed installer status")
        return parts[0], int(parts[1])

    def wait_for_stack(self) -> None:
        deadline = self.runner.monotonic() + self.wait_seconds
        health_services = ("postgres", *(service for _key, service in AUTHORITIES))
        installers = tuple(f"{service}-state-install" for _key, service in AUTHORITIES)
        last_pending: list[str] = []
        while self.runner.monotonic() < deadline:
            pending: list[str] = []
            failed: list[str] = []
            for service in health_services:
                container = self.service_container_id(service)
                if not container:
                    pending.append(f"{service}=missing")
                    continue
                status = self._container_health(container)
                if status != "healthy":
                    pending.append(f"{service}={status or 'unknown'}")
            for service in installers:
                container = self.service_container_id(service, include_stopped=True)
                if not container:
                    pending.append(f"{service}=missing")
                    continue
                status, exit_code = self._installer_status(container)
                if status == "exited" and exit_code == 0:
                    continue
                if status == "exited":
                    failed.append(f"{service}=exit-{exit_code}")
                else:
                    pending.append(f"{service}={status}")
            if failed:
                raise GateError("Notary state installer failed: " + ", ".join(failed))
            if not pending:
                return
            last_pending = pending
            self.runner.sleep(2.0)
        detail = ", ".join(last_pending) if last_pending else "unknown status"
        raise GateError(f"stack did not become healthy within the deadline: {detail}")

    def doctor_all(self) -> None:
        for _authority, service in AUTHORITIES:
            self._compose(
                "run",
                "--rm",
                "--no-deps",
                service,
                "--config",
                "/etc/registry-notary/notary.yaml",
                "state",
                "doctor",
            )
            print(f"notary-state: {service} doctor passed")

    def validate_runtime_mount(self, container_id: str) -> None:
        mounts_output = self._run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container_id]
        )
        labels_output = self._run(
            [
                "docker",
                "volume",
                "inspect",
                "--format",
                "{{json .Labels}}",
                self.expected_volume,
            ]
        )
        try:
            mounts = json.loads(mounts_output)
            labels = json.loads(labels_output)
        except json.JSONDecodeError as error:
            raise GateError("Docker returned invalid mount metadata") from error
        validate_runtime_pgdata_mounts(
            mounts,
            expected_volume=self.expected_volume,
            volume_labels=labels,
            compose_project_name=self.compose_project_name,
        )

    def _postgres_query(self, database: str, sql: str) -> str:
        return self._compose(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-eu",
            "-c",
            'exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -Atc "$2"',
            "notary-state",
            database,
            sql,
        )

    @staticmethod
    def _counts_sql() -> str:
        branches = [
            f"SELECT '{table}'::text AS table_name, count(*)::bigint AS row_count "
            f"FROM registry_notary_private.{table}"
            for table in CORRECTNESS_TABLES
        ]
        return (
            "WITH correctness_counts AS ("
            + " UNION ALL ".join(branches)
            + ") SELECT table_name || '|' || row_count::text "
            "FROM correctness_counts ORDER BY table_name"
        )

    def capture_snapshot(self) -> StateSnapshot:
        container_id = self.service_container_id("postgres")
        if not container_id:
            raise GateError("PostgreSQL container is not running")
        self.validate_runtime_mount(container_id)
        control = self._postgres_query(
            "solmara_lab",
            "SELECT system_identifier FROM pg_control_system(); "
            "SHOW server_version_num; SHOW data_directory",
        )
        system_identifier, server_version_num, data_directory = parse_control_snapshot(
            control
        )
        rows: list[tuple[str, str, int]] = []
        query = self._counts_sql()
        for authority, _service in AUTHORITIES:
            parsed = parse_authority_counts(
                authority,
                self._postgres_query(f"solmara_notary_{authority}", query),
            )
            rows.extend(
                (authority, table, parsed[table]) for table in CORRECTNESS_TABLES
            )
        return StateSnapshot(
            container_id=container_id,
            system_identifier=system_identifier,
            server_version_num=server_version_num,
            data_directory=data_directory,
            volume_name=self.expected_volume,
            counts=tuple(sorted(rows)),
        )

    def run_just(self, recipe: str) -> None:
        output = self._run(["just", recipe])
        if output:
            print(output, end="" if output.endswith("\n") else "\n")

    def run_gate(self) -> StateSnapshot:
        self.resolve_compose()
        self.wait_for_stack()
        self.doctor_all()
        before = self.capture_snapshot()

        self.run_just("down")
        if self.service_container_id("postgres", include_stopped=True):
            raise GateError("just down did not remove the PostgreSQL container")
        self.run_just("up")

        self.wait_for_stack()
        # No doctor or scenario request may move above this snapshot. Installer
        # schema metadata and readiness probes are deliberately excluded from
        # the nine correctness-state tables.
        after = self.capture_snapshot()
        compare_snapshots(before, after)
        self.doctor_all()

        totals = after.totals()
        rendered_totals = ", ".join(
            f"{authority}={totals[authority]}" for authority, _service in AUTHORITIES
        )
        print(
            "notary-state: just down/up preserved PostgreSQL system_identifier "
            f"{after.system_identifier} on {after.volume_name}"
        )
        print(f"notary-state: preserved correctness rows: {rendered_totals}")
        return after


def main() -> int:
    try:
        RestartPersistenceGate().run_gate()
    except GateError as error:
        print(f"notary-state: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
