"""Deterministic tests for the Notary PostgreSQL restart-persistence gate."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).with_name("notary_state_restart.py")
SPEC = importlib.util.spec_from_file_location("notary_state_restart", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"could not load {SCRIPT}")
restart = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = restart
SPEC.loader.exec_module(restart)


def valid_compose_config() -> dict[str, object]:
    return {
        "services": {
            "postgres": {
                "volumes": [
                    {
                        "type": "volume",
                        "source": "postgres-data",
                        "target": "/var/lib/postgresql/data",
                        "read_only": False,
                    }
                ]
            }
        },
        "volumes": {"postgres-data": {"name": "demo_postgres-data"}},
    }


def valid_counts(*, increment: int = 0) -> tuple[tuple[str, str, int], ...]:
    rows = []
    for authority_index, (authority, _service) in enumerate(restart.AUTHORITIES):
        for table_index, table in enumerate(restart.CORRECTNESS_TABLES):
            rows.append(
                (authority, table, authority_index + table_index + 1 + increment)
            )
    return tuple(sorted(rows))


def snapshot(
    *,
    container_id: str = "postgres-before",
    system_identifier: str = "7541234567890123456",
    version: int = 160010,
    data_directory: str = "/var/lib/postgresql/data",
    volume_name: str = "demo_postgres-data",
    counts: tuple[tuple[str, str, int], ...] | None = None,
) -> restart.StateSnapshot:
    return restart.StateSnapshot(
        container_id=container_id,
        system_identifier=system_identifier,
        server_version_num=version,
        data_directory=data_directory,
        volume_name=volume_name,
        counts=valid_counts() if counts is None else counts,
    )


class RecordingRunner:
    def __init__(self, *, outputs: list[str] | None = None) -> None:
        self.calls: list[tuple[list[str], Path, dict[str, str]]] = []
        self.outputs = list(outputs or [])
        self.now = 0.0

    def run(
        self,
        command: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> str:
        self.calls.append((list(command), cwd, dict(env)))
        return self.outputs.pop(0) if self.outputs else ""

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ComposeLayoutTests(unittest.TestCase):
    def test_accepts_exact_postgresql_16_named_volume(self) -> None:
        self.assertEqual(
            restart.validate_compose_pgdata_layout(valid_compose_config()),
            "demo_postgres-data",
        )

    def test_rejects_nonexact_storage_mounts(self) -> None:
        invalid_mounts = (
            {
                "type": "volume",
                "source": "other",
                "target": "/var/lib/postgresql/data",
            },
            {
                "type": "bind",
                "source": "./postgres-data",
                "target": "/var/lib/postgresql/data",
            },
            {
                "type": "volume",
                "source": "postgres-data",
                "target": "/var/lib/postgresql/data",
                "read_only": True,
            },
            {
                "type": "volume",
                "source": "postgres-data",
                "target": "/var/lib/postgresql",
            },
            {
                "type": "volume",
                "source": "postgres-data",
                "target": "/var/lib/postgresql/data/nested",
            },
        )
        for mount in invalid_mounts:
            with self.subTest(mount=mount):
                config = valid_compose_config()
                config["services"]["postgres"]["volumes"] = [mount]
                with self.assertRaises(restart.GateError):
                    restart.validate_compose_pgdata_layout(config)

    def test_rejects_second_mount_above_pgdata(self) -> None:
        config = valid_compose_config()
        config["services"]["postgres"]["volumes"].append(
            {
                "type": "bind",
                "source": "/tmp",
                "target": "/var/lib",
            }
        )
        with self.assertRaises(restart.GateError):
            restart.validate_compose_pgdata_layout(config)


class RuntimeMountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mount = {
            "Type": "volume",
            "Name": "demo_postgres-data",
            "Destination": "/var/lib/postgresql/data",
            "RW": True,
        }
        self.labels = {
            "com.docker.compose.project": "demo",
            "com.docker.compose.volume": "postgres-data",
        }

    def validate(self, mounts: object, labels: object | None = None) -> None:
        restart.validate_runtime_pgdata_mounts(
            mounts,
            expected_volume="demo_postgres-data",
            volume_labels=self.labels if labels is None else labels,
            compose_project_name="demo",
        )

    def test_accepts_exact_runtime_mount_and_labels(self) -> None:
        self.validate([self.mount])

    def test_rejects_anonymous_bind_readonly_parent_and_nested_mounts(self) -> None:
        changes = (
            {"Name": ""},
            {"Type": "bind"},
            {"RW": False},
            {"Destination": "/var/lib/postgresql"},
            {"Destination": "/var/lib/postgresql/data/nested"},
        )
        for change in changes:
            with self.subTest(change=change):
                mount = {**self.mount, **change}
                with self.assertRaises(restart.GateError):
                    self.validate([mount])

    def test_rejects_any_overlapping_second_mount(self) -> None:
        for destination in (
            "/",
            "/var/lib",
            "/var/lib/postgresql",
            "/var/lib/postgresql/data/nested",
        ):
            with self.subTest(destination=destination):
                overlapping = {
                    "Type": "bind",
                    "Source": "/tmp",
                    "Destination": destination,
                    "RW": True,
                }
                with self.assertRaises(restart.GateError):
                    self.validate([self.mount, overlapping])

    def test_rejects_wrong_compose_ownership_labels(self) -> None:
        for key in self.labels:
            with self.subTest(key=key):
                labels = {**self.labels, key: "other"}
                with self.assertRaises(restart.GateError):
                    self.validate([self.mount], labels)


class SnapshotParsingTests(unittest.TestCase):
    def test_parses_postgresql_16_control_snapshot(self) -> None:
        self.assertEqual(
            restart.parse_control_snapshot(
                "7541234567890123456\n160010\n/var/lib/postgresql/data\n"
            ),
            ("7541234567890123456", 160010, "/var/lib/postgresql/data"),
        )

    def test_rejects_wrong_major_or_data_directory(self) -> None:
        for output in (
            "7541234567890123456\n170001\n/var/lib/postgresql/data\n",
            "7541234567890123456\n160010\n/var/lib/postgresql/16/docker\n",
            "not-a-number\n160010\n/var/lib/postgresql/data\n",
        ):
            with self.subTest(output=output):
                with self.assertRaises(restart.GateError):
                    restart.parse_control_snapshot(output)

    def test_parses_exact_nine_authority_counts(self) -> None:
        output = "\n".join(
            f"{table}|{index + 1}"
            for index, table in enumerate(restart.CORRECTNESS_TABLES)
        )
        parsed = restart.parse_authority_counts("cra", output)
        self.assertEqual(set(parsed), set(restart.CORRECTNESS_TABLES))
        self.assertEqual(sum(parsed.values()), 45)

    def test_rejects_zero_missing_duplicate_or_unknown_counts(self) -> None:
        valid_lines = [
            f"{table}|1" for table in restart.CORRECTNESS_TABLES
        ]
        invalid = (
            [f"{table}|0" for table in restart.CORRECTNESS_TABLES],
            valid_lines[:-1],
            [*valid_lines, valid_lines[0]],
            [*valid_lines[:-1], "schema_metadata|1"],
        )
        for lines in invalid:
            with self.subTest(lines=lines):
                with self.assertRaises(restart.GateError):
                    restart.parse_authority_counts("cra", "\n".join(lines))

    def test_count_query_has_only_the_nine_correctness_tables(self) -> None:
        query = restart.RestartPersistenceGate._counts_sql()
        for table in restart.CORRECTNESS_TABLES:
            self.assertIn(f"registry_notary_private.{table}", query)
        self.assertNotIn("schema_metadata", query)
        self.assertEqual(query.count("count(*)"), 9)


class SnapshotComparisonTests(unittest.TestCase):
    def test_accepts_replacement_container_with_identical_state(self) -> None:
        restart.compare_snapshots(
            snapshot(container_id="postgres-before"),
            snapshot(container_id="postgres-after"),
        )

    def test_rejects_reused_container_or_changed_identity_metadata_and_counts(self) -> None:
        after_changes = (
            {},
            {"container_id": "postgres-after", "system_identifier": "123"},
            {"container_id": "postgres-after", "version": 160011},
            {
                "container_id": "postgres-after",
                "data_directory": "/var/lib/postgresql/other",
            },
            {"container_id": "postgres-after", "volume_name": "other"},
            {
                "container_id": "postgres-after",
                "counts": valid_counts(increment=1),
            },
        )
        before = snapshot()
        for change in after_changes:
            with self.subTest(change=change):
                with self.assertRaises(restart.GateError):
                    restart.compare_snapshots(before, snapshot(**change))


class ResolveComposeTests(unittest.TestCase):
    def test_preserves_explicit_project_and_inherited_image_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".env", "versions.env", "compose.yaml"):
                (root / name).touch()
            runner = RecordingRunner(outputs=[json.dumps(valid_compose_config())])
            environment = {
                "COMPOSE_PROJECT_NAME": "explicit-project",
                "POSTGRES_IMAGE": "postgres:16.99",
                "REGISTRY_NOTARY_IMAGE": "notary:test",
            }
            gate = restart.RestartPersistenceGate(
                root=root,
                runner=runner,
                environ=environment,
            )

            gate.resolve_compose()

            self.assertEqual(gate.compose_project_name, "explicit-project")
            self.assertEqual(gate.expected_volume, "demo_postgres-data")
            self.assertEqual(len(runner.calls), 1)
            command, cwd, used_environment = runner.calls[0]
            self.assertEqual(command[-3:], ["config", "--format", "json"])
            self.assertEqual(cwd, root.resolve())
            self.assertEqual(used_environment, environment)


class WaitForStackTests(unittest.TestCase):
    class HealthyRunner(RecordingRunner):
        def __init__(self, *, installer_exit_code: int = 0) -> None:
            super().__init__()
            self.installer_exit_code = installer_exit_code

        def run(
            self,
            command: list[str] | tuple[str, ...],
            *,
            cwd: Path,
            env: dict[str, str],
        ) -> str:
            command = list(command)
            self.calls.append((command, cwd, dict(env)))
            if "ps" in command and "-q" in command:
                return "container-" + command[-1]
            if command[:3] == ["docker", "inspect", "--format"]:
                template = command[3]
                if "ExitCode" in template:
                    return f"exited|{self.installer_exit_code}"
                return "healthy"
            raise AssertionError(f"unexpected command: {command}")

    def gate(self, runner: RecordingRunner) -> restart.RestartPersistenceGate:
        gate = restart.RestartPersistenceGate(
            root=Path.cwd(),
            runner=runner,
            environ={"COMPOSE_PROJECT_NAME": "demo"},
            wait_seconds=5,
        )
        gate.compose = ["docker", "compose"]
        return gate

    def test_waits_for_all_healthchecks_and_installers(self) -> None:
        runner = self.HealthyRunner()
        self.gate(runner).wait_for_stack()
        compose_ps = [call[0] for call in runner.calls if "ps" in call[0]]
        self.assertEqual(len(compose_ps), 13)
        installer_services = {
            command[-1] for command in compose_ps if "--all" in command
        }
        self.assertEqual(
            installer_services,
            {
                f"{service}-state-install"
                for _authority, service in restart.AUTHORITIES
            },
        )
        self.assertEqual(runner.now, 0.0)

    def test_fails_immediately_when_an_installer_exits_nonzero(self) -> None:
        runner = self.HealthyRunner(installer_exit_code=7)
        with self.assertRaisesRegex(restart.GateError, "installer failed"):
            self.gate(runner).wait_for_stack()

    def test_times_out_with_the_pending_service(self) -> None:
        runner = self.HealthyRunner()

        def unhealthy_run(
            command: list[str] | tuple[str, ...],
            *,
            cwd: Path,
            env: dict[str, str],
        ) -> str:
            output = WaitForStackTests.HealthyRunner.run(
                runner, command, cwd=cwd, env=env
            )
            if command[:3] == ["docker", "inspect", "--format"]:
                if "ExitCode" not in command[3]:
                    return "starting"
            return output

        runner.run = unhealthy_run
        with self.assertRaisesRegex(restart.GateError, "postgres=starting"):
            self.gate(runner).wait_for_stack()
        self.assertGreaterEqual(runner.now, 5.0)


class OrchestrationTests(unittest.TestCase):
    class HarnessGate(restart.RestartPersistenceGate):
        def __init__(self, runner: RecordingRunner, events: list[str]) -> None:
            super().__init__(
                root=Path.cwd(),
                runner=runner,
                environ={
                    "COMPOSE_PROJECT_NAME": "explicit-project",
                    "POSTGRES_IMAGE": "postgres:16.99",
                    "REGISTRY_NOTARY_IMAGE": "notary:test",
                },
            )
            self.events = events
            self.snapshots = [
                snapshot(container_id="postgres-before"),
                snapshot(container_id="postgres-after"),
            ]

        def resolve_compose(self) -> None:
            self.events.append("resolve")
            self.compose_project_name = self.env["COMPOSE_PROJECT_NAME"]
            self.compose = ["docker", "compose"]
            self.expected_volume = "demo_postgres-data"

        def wait_for_stack(self) -> None:
            self.events.append("wait")

        def doctor_all(self) -> None:
            self.events.append("doctor")

        def capture_snapshot(self) -> restart.StateSnapshot:
            name = "capture-before" if len(self.snapshots) == 2 else "capture-after"
            self.events.append(name)
            return self.snapshots.pop(0)

        def service_container_id(
            self, service: str, *, include_stopped: bool = False
        ) -> str:
            self.events.append(f"assert-removed:{service}:{include_stopped}")
            return ""

    def test_exact_down_up_order_and_inherited_environment(self) -> None:
        events: list[str] = []
        runner = RecordingRunner()
        gate = self.HarnessGate(runner, events)

        with redirect_stdout(io.StringIO()):
            gate.run_gate()

        self.assertEqual(
            events,
            [
                "resolve",
                "wait",
                "doctor",
                "capture-before",
                "assert-removed:postgres:True",
                "wait",
                "capture-after",
                "doctor",
            ],
        )
        self.assertEqual([call[0] for call in runner.calls], [["just", "down"], ["just", "up"]])
        for _command, cwd, environment in runner.calls:
            self.assertEqual(cwd, Path.cwd().resolve())
            self.assertEqual(environment["COMPOSE_PROJECT_NAME"], "explicit-project")
            self.assertEqual(environment["POSTGRES_IMAGE"], "postgres:16.99")
            self.assertEqual(environment["REGISTRY_NOTARY_IMAGE"], "notary:test")

    def test_command_failure_stops_before_up(self) -> None:
        class FailingRunner(RecordingRunner):
            def run(self, command, *, cwd, env):
                super().run(command, cwd=cwd, env=env)
                raise restart.CommandError("down failed")

        events: list[str] = []
        runner = FailingRunner()
        gate = self.HarnessGate(runner, events)
        with self.assertRaisesRegex(restart.CommandError, "down failed"):
            gate.run_gate()
        self.assertEqual([call[0] for call in runner.calls], [["just", "down"]])
        self.assertEqual(events[-1], "capture-before")


if __name__ == "__main__":
    unittest.main()
