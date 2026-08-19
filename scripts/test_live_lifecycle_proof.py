from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).with_name("live-lifecycle-proof.py")
SPEC = importlib.util.spec_from_file_location("live_lifecycle_proof", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
lifecycle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lifecycle
SPEC.loader.exec_module(lifecycle)


class FakeOperations:
    def __init__(self, fail_at: str = "", *, hot_reload_sro: bool = False) -> None:
        self.fail_at = fail_at
        self.hot_reload_sro = hot_reload_sro
        self.events: list[str] = []
        self.mosd_duplicate = False
        self.sro_changed = False
        self.sro_bound = False
        self.original_binding = b"original-binding"
        self.original_mosd_fixture = lifecycle.MosdFixture(True)
        self.mosd_generation = "mosd-generation"
        self.sro_generation = "sro-generation-1"
        self.publication = lifecycle.ExtractPublication(
            Path("private-publication"),
            "/private/extract",
            "private-extract-id",
        )

    def _event(self, name: str) -> None:
        self.events.append(name)
        if self.fail_at == name:
            raise RuntimeError(
                "selector=2300010248 token=private source row private.sqlite"
            )

    def load_environment(self) -> None:
        self._event("load")

    def validate_preconditions(self) -> None:
        self._event("preconditions")

    def observe_evidence(self, requirement: str) -> bool:
        name = (
            "observe-mosd"
            if requirement == lifecycle.MOSD_REQUIREMENT
            else "observe-sro"
        )
        self._event(name)
        return (
            not self.mosd_duplicate if name == "observe-mosd" else not self.sro_changed
        )

    def generation(self, service: str) -> str:
        name = (
            "generation-sro" if service == lifecycle.SRO_SERVICE else "generation-mosd"
        )
        self._event(name)
        return (
            self.sro_generation
            if service == lifecycle.SRO_SERVICE
            else self.mosd_generation
        )

    def capture_mosd_fixture(self):
        self._event("capture-mosd")
        return self.original_mosd_fixture

    def mutate_mosd(self, duplicate: bool) -> None:
        self._event(f"mutate-mosd-{str(duplicate).lower()}")
        self.mosd_duplicate = duplicate

    def restore_mosd_fixture(self, fixture) -> None:
        self._event("restore-mosd")
        if fixture != self.original_mosd_fixture:
            raise AssertionError
        self.mosd_duplicate = False

    def capture_sro_binding(self) -> bytes:
        self._event("capture-binding")
        return self.original_binding

    def publish_changed_sro(self):
        self._event("publish-sro")
        return self.publication

    def bind_sro(self, publication) -> None:
        self._event("bind-sro")
        if publication is not self.publication:
            raise AssertionError
        self.sro_bound = True
        if self.hot_reload_sro:
            self.sro_changed = True

    def restart_sro(self) -> None:
        self._event("restart-sro")
        self.sro_changed = self.sro_bound
        self.sro_generation = (
            "sro-generation-2" if self.sro_bound else "sro-generation-restored"
        )

    def wait_sro_ready(self) -> None:
        self._event("wait-sro")

    def prove_replacement_refusals(self) -> None:
        self._event("replacement-refusals")

    def restore_sro_binding(self, original: bytes) -> None:
        self._event("restore-binding")
        if original != self.original_binding:
            raise AssertionError
        self.sro_bound = False

    def discard_sro_publication(self, publication) -> None:
        self._event("discard-sro")
        if publication is not self.publication or self.sro_bound:
            raise AssertionError


class LiveLifecycleProofTests(unittest.TestCase):
    def test_complete_proof_uses_signed_http_observations_and_restores_state(
        self,
    ) -> None:
        operations = FakeOperations()

        result = lifecycle.run_proof(operations)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["proof"], "live-http")
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(operations.mosd_duplicate)
        self.assertFalse(operations.sro_bound)
        self.assertFalse(operations.sro_changed)
        self.assertIn("discard-sro", operations.events)
        self.assertIn("replacement-refusals", operations.events)
        self.assertGreaterEqual(operations.events.count("observe-mosd"), 3)
        self.assertGreaterEqual(operations.events.count("observe-sro"), 4)

    def test_failure_after_live_mutation_restores_mosd_and_sro(self) -> None:
        operations = FakeOperations(fail_at="replacement-refusals")

        with self.assertRaisesRegex(
            lifecycle.LifecycleProofError,
            "lifecycle proof did not complete",
        ):
            lifecycle.run_proof(operations)

        self.assertFalse(operations.mosd_duplicate)
        self.assertFalse(operations.sro_bound)
        self.assertFalse(operations.sro_changed)
        self.assertIn("restore-binding", operations.events)
        self.assertGreaterEqual(operations.events.count("restart-sro"), 2)

    def test_failure_before_binding_capture_restores_captured_mosd(self) -> None:
        operations = FakeOperations(fail_at="capture-binding")

        with self.assertRaises(lifecycle.LifecycleProofError):
            lifecycle.run_proof(operations)

        self.assertFalse(operations.mosd_duplicate)
        self.assertIn("restore-mosd", operations.events)
        self.assertNotIn("restore-binding", operations.events)

    def test_cleanup_failure_wins_without_exposing_private_details(self) -> None:
        operations = FakeOperations(fail_at="restore-mosd")

        with self.assertRaisesRegex(
            lifecycle.LifecycleProofError,
            "lifecycle proof did not complete",
        ) as caught:
            lifecycle.run_proof(operations)

        rendered = str(caught.exception).lower()
        for forbidden in ("2300010248", "selector", "token", "sqlite", "source row"):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("restore-binding", operations.events)
        self.assertIn("discard-sro", operations.events)
        self.assertFalse(operations.sro_bound)

    def test_failure_while_binding_still_discards_unbound_publication(self) -> None:
        operations = FakeOperations(fail_at="bind-sro")

        with self.assertRaises(lifecycle.LifecycleProofError):
            lifecycle.run_proof(operations)

        self.assertIn("restore-binding", operations.events)
        self.assertIn("discard-sro", operations.events)
        self.assertFalse(operations.mosd_duplicate)

    def test_hot_reloaded_sro_binding_is_rejected_before_restart(self) -> None:
        operations = FakeOperations(hot_reload_sro=True)

        with self.assertRaises(lifecycle.LifecycleProofError):
            lifecycle.run_proof(operations)

        binding_index = operations.events.index("bind-sro")
        restart_index = operations.events.index("restart-sro")
        self.assertIn("observe-sro", operations.events[binding_index:restart_index])
        self.assertFalse(operations.sro_bound)
        self.assertFalse(operations.sro_changed)

    def test_changed_extract_is_staged_then_published_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publication = lifecycle._publish_changed_sro(root)
            try:
                self.assertTrue(publication.path.is_file())
                self.assertEqual(
                    stat.S_IMODE(publication.path.stat().st_mode) & 0o222,
                    0,
                )
                lifecycle.publisher.validate_extract(
                    publication.path,
                    "sro",
                    observed_at=lifecycle._timestamp(lifecycle._now()),
                    expected_extract_id=publication.extract_id,
                )
                with sqlite3.connect(publication.path) as connection:
                    row = connection.execute(
                        "SELECT poverty_band FROM poverty_evidence WHERE uin = ?",
                        (lifecycle.SRO_CONTROL_SUBJECT,),
                    ).fetchone()
                self.assertEqual(row, ("standard",))
                self.assertEqual(list((root / "runtime").glob(".lifecycle-sro-*")), [])
            finally:
                publication.path.unlink(missing_ok=True)

    def test_failed_publication_validation_leaves_no_replacement_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = lifecycle.publisher.validate_extract
            lifecycle.publisher.validate_extract = lambda *args, **kwargs: (
                _ for _ in ()
            ).throw(RuntimeError("private validation detail"))
            try:
                with self.assertRaises(RuntimeError):
                    lifecycle._publish_changed_sro(root)
            finally:
                lifecycle.publisher.validate_extract = original

            extracts = root / lifecycle.publisher.EVIDENCE_DIRECTORY
            self.assertEqual(list(extracts.glob("*.sqlite")), [])

    def test_mosd_lifecycle_uses_only_fixed_publisher_verbs(self) -> None:
        commands: list[list[str]] = []
        original = lifecycle._run_command

        def record(command, **kwargs):
            commands.append(command)
            return lifecycle.subprocess.CompletedProcess(command, 0, "", "")

        lifecycle._run_command = record
        try:
            operations = lifecycle.LocalOperations(Path("/unused"))
            fixture = operations.capture_mosd_fixture()
            operations.mutate_mosd(True)
            operations.restore_mosd_fixture(fixture)
        finally:
            lifecycle._run_command = original

        self.assertEqual(
            [command[-1] for command in commands],
            ["begin-proof", "set-proof-state", "restore-proof"],
        )
        expected_prefix = [
            "run",
            "--rm",
            "-T",
            "--no-deps",
            lifecycle.MOSD_PUBLISHER_SERVICE,
        ]
        for command in commands:
            self.assertEqual(command[-6:-1], expected_prefix)
            rendered = " ".join(command).lower()
            self.assertNotIn(lifecycle.MOSD_CONTROL_SUBJECT, rendered)
            self.assertNotIn("duplicate", rendered)

    def test_failed_mosd_begin_attempts_idempotent_publisher_restore(self) -> None:
        commands: list[list[str]] = []
        original = lifecycle._run_command

        def fail_begin(command, **kwargs):
            commands.append(command)
            if command[-1] == "begin-proof":
                raise RuntimeError("private publisher failure")
            return lifecycle.subprocess.CompletedProcess(command, 0, "", "")

        lifecycle._run_command = fail_begin
        try:
            with self.assertRaisesRegex(
                lifecycle.LifecycleProofError,
                "lifecycle proof did not complete",
            ):
                lifecycle.LocalOperations(Path("/unused")).capture_mosd_fixture()
        finally:
            lifecycle._run_command = original

        self.assertEqual(
            [command[-1] for command in commands],
            ["begin-proof", "restore-proof"],
        )

    def test_mosd_relay_requires_its_project_named_volume_read_only(self) -> None:
        operations = lifecycle.LocalOperations(Path("/unused"))
        original_command = lifecycle._run_command
        original_project = os.environ.get("COMPOSE_PROJECT_NAME")
        os.environ["COMPOSE_PROJECT_NAME"] = "solmara-test"
        commands: list[list[str]] = []
        responses = iter(
            (
                lifecycle.subprocess.CompletedProcess([], 0, "relay-container\n", ""),
                lifecycle.subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        [
                            {
                                "Type": "volume",
                                "Name": "solmara-test_mosd-relay-source",
                                "Destination": "/var/lib/relay/source",
                                "RW": False,
                            }
                        ]
                    ),
                    "",
                ),
            )
        )

        def respond(command, **kwargs):
            commands.append(command)
            return next(responses)

        lifecycle._run_command = respond
        try:
            operations._require_read_only_named_volume(
                lifecycle.MOSD_RELAY_SERVICE,
                lifecycle.MOSD_SOURCE_VOLUME,
                lifecycle.RELAY_SOURCE_DESTINATION,
            )
        finally:
            lifecycle._run_command = original_command
            if original_project is None:
                os.environ.pop("COMPOSE_PROJECT_NAME", None)
            else:
                os.environ["COMPOSE_PROJECT_NAME"] = original_project

        self.assertIn("ps", commands[0])
        self.assertEqual(commands[1][:2], ["docker", "inspect"])

    def test_writable_or_bind_mosd_source_mount_is_refused(self) -> None:
        operations = lifecycle.LocalOperations(Path("/unused"))
        original_command = lifecycle._run_command
        original_project = os.environ.get("COMPOSE_PROJECT_NAME")
        os.environ["COMPOSE_PROJECT_NAME"] = "solmara-test"
        cases = (
            {"Type": "volume", "RW": True},
            {"Type": "bind", "RW": False},
        )
        try:
            for changed in cases:
                with self.subTest(changed=changed):
                    mount = {
                        "Type": "volume",
                        "Name": "solmara-test_mosd-relay-source",
                        "Destination": "/var/lib/relay/source",
                        "RW": False,
                        **changed,
                    }
                    responses = iter(
                        (
                            lifecycle.subprocess.CompletedProcess(
                                [], 0, "relay-container\n", ""
                            ),
                            lifecycle.subprocess.CompletedProcess(
                                [], 0, json.dumps([mount]), ""
                            ),
                        )
                    )
                    lifecycle._run_command = lambda command, **kwargs: next(responses)
                    with self.assertRaises(lifecycle.LifecycleProofError):
                        operations._require_read_only_named_volume(
                            lifecycle.MOSD_RELAY_SERVICE,
                            lifecycle.MOSD_SOURCE_VOLUME,
                            lifecycle.RELAY_SOURCE_DESTINATION,
                        )
        finally:
            lifecycle._run_command = original_command
            if original_project is None:
                os.environ.pop("COMPOSE_PROJECT_NAME", None)
            else:
                os.environ["COMPOSE_PROJECT_NAME"] = original_project

    def test_runtime_patch_changes_only_the_bound_extract_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary) / "runtime.yaml"
            old_path = (
                "/var/lib/registry-evidence/sro/extracts/"
                "sro-poverty-20260812T010203Z.sqlite"
            )
            new_path = (
                "/var/lib/registry-evidence/sro/extracts/"
                "sro-poverty-20260812T020304Z.sqlite"
            )
            original = (
                "version: 1\n"
                "# operator-generated runtime\n"
                "sourceExtracts:\n"
                f"  sro-poverty-extract: {{ path: {old_path} }}\n"
            ).encode()
            runtime.write_bytes(original)

            lifecycle._replace_runtime_binding(runtime, new_path)

            self.assertEqual(
                runtime.read_bytes(),
                original.replace(old_path.encode(), new_path.encode()),
            )

    def test_ready_sro_with_invalid_source_requires_evidence_failure(self) -> None:
        operations = lifecycle.LocalOperations(Path("/unused"))
        original_http_json = lifecycle.evidence_common.http_json
        original_monotonic = lifecycle.time.monotonic
        original_sleep = lifecycle.time.sleep
        original_observe = operations.observe_evidence
        lifecycle.evidence_common.http_json = lambda *args, **kwargs: (
            lifecycle.evidence_common.StepHttpResult(200, {}, {})
        )
        clock = iter((0.0, 0.0, lifecycle.REFUSAL_OBSERVATION_SECONDS + 1.0))
        lifecycle.time.monotonic = lambda: next(clock)
        lifecycle.time.sleep = lambda _seconds: None

        def refused(_requirement: str) -> bool:
            raise lifecycle.LifecycleProofError("private runtime detail")

        operations.observe_evidence = refused
        try:
            operations._wait_sro_refused()
        finally:
            lifecycle.evidence_common.http_json = original_http_json
            lifecycle.time.monotonic = original_monotonic
            lifecycle.time.sleep = original_sleep
            operations.observe_evidence = original_observe

    def test_ready_sro_with_invalid_source_rejects_successful_evidence(self) -> None:
        operations = lifecycle.LocalOperations(Path("/unused"))
        original_monotonic = lifecycle.time.monotonic
        original_observe = operations.observe_evidence
        clock = iter((0.0, lifecycle.REFUSAL_OBSERVATION_SECONDS + 1.0))
        lifecycle.time.monotonic = lambda: next(clock)
        operations.observe_evidence = lambda _requirement: True
        try:
            with self.assertRaisesRegex(
                lifecycle.LifecycleProofError,
                "lifecycle proof did not complete",
            ):
                operations._wait_sro_refused()
        finally:
            lifecycle.time.monotonic = original_monotonic
            operations.observe_evidence = original_observe

    def test_cli_failure_emits_only_the_public_failure_class(self) -> None:
        original = lifecycle.run_proof
        lifecycle.run_proof = lambda: (_ for _ in ()).throw(
            RuntimeError("selector=2300010248 token=private signed.jws")
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = lifecycle.main(["--json"])
        finally:
            lifecycle.run_proof = original

        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "live-lifecycle-proof: failed\n")

    def test_success_document_contains_only_sanitized_named_checks(self) -> None:
        result = lifecycle.run_proof(FakeOperations())
        rendered = json.dumps(result, sort_keys=True)

        lifecycle._assert_sanitized(rendered)
        for forbidden in (
            lifecycle.MOSD_CONTROL_SUBJECT,
            lifecycle.SRO_CONTROL_SUBJECT,
            "selector",
            "token",
            "jws",
            "signature",
            "sqlite",
            "source row",
        ):
            self.assertNotIn(forbidden.lower(), rendered.lower())


if __name__ == "__main__":
    unittest.main()
