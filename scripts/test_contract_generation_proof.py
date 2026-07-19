from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_proof():
    spec = importlib.util.spec_from_file_location(
        "contract_generation_proof", ROOT / "scripts" / "contract-generation-proof.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load contract-generation-proof.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["contract_generation_proof"] = module
    spec.loader.exec_module(module)
    return module


class ContractGenerationProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proof = load_proof()

    def test_successor_is_a_revision_only_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "sro-social"
            source = ROOT / "projects" / "sro-social"
            shutil.copytree(source, project)
            integration = (
                project
                / "integrations"
                / "child-benefit-household-by-uin"
                / "integration.yaml"
            )
            before = yaml.safe_load(integration.read_text(encoding="utf-8"))
            self.proof.make_successor(project)
            after = yaml.safe_load(integration.read_text(encoding="utf-8"))
            self.assertEqual(before | {"revision": 2}, after)

    def test_mixed_override_replaces_only_notary_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generation = root / "green"
            (generation / "relay").mkdir(parents=True)
            (generation / "notary").mkdir()
            override = root / "mixed.yaml"
            self.proof.write_override(override, generation, relay=False, notary=True)
            services = yaml.safe_load(override.read_text(encoding="utf-8"))["services"]
            self.assertEqual(set(services), {"sro-notary", "sro-notary-state-install"})
            self.assertNotIn("sro-social-relay", services)
            self.assertIn(
                f"{generation / 'notary' / 'notary.yaml'}:/etc/registry-notary/notary.yaml:ro",
                services["sro-notary"]["volumes"],
            )

    def test_success_response_must_be_minimized_and_subject_free(self) -> None:
        response = {
            "results": [
                {
                    "claim_id": self.proof.CLAIM_ID,
                    "disclosure": "predicate",
                    "satisfied": True,
                }
            ]
        }
        self.assertTrue(
            self.proof.successful_evaluation(response, self.proof.BLUE_SUBJECT)
        )
        response["debug"] = self.proof.BLUE_SUBJECT
        self.assertFalse(
            self.proof.successful_evaluation(response, self.proof.BLUE_SUBJECT)
        )

    def test_sensitive_scan_reports_category_without_value(self) -> None:
        secret = b"synthetic-secret-value"
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "captured.log"
            artifact.write_bytes(b"prefix " + secret + b" suffix")
            with self.assertRaises(self.proof.ProofFailure) as rejected:
                self.proof.scan_paths([artifact], {"test credential": secret})
            message = str(rejected.exception)
            self.assertIn("test credential", message)
            self.assertNotIn(secret.decode("utf-8"), message)

    def test_failed_command_output_is_actionable_bounded_and_redacted(self) -> None:
        secret = "runtime-secret-that-must-not-appear"
        output_lines = "\n".join(f"diagnostic line {index}" for index in range(40))
        command = (
            'printf "%s\\n" "explanation: registry image was unavailable" '
            '"$INHERITED_TOKEN" "2300027390"; '
            f'printf "%s\\n" "{output_lines}"; exit 7'
        )
        with mock.patch.dict(os.environ, {"INHERITED_TOKEN": secret}, clear=False):
            with self.assertRaises(self.proof.ProofFailure) as rejected:
                self.proof.run(["/bin/sh", "-c", command])
        message = str(rejected.exception)
        self.assertIn("explanation: registry image was unavailable", message)
        self.assertIn("command output (redacted and bounded)", message)
        self.assertNotIn(secret, message)
        self.assertNotIn(self.proof.BLUE_SUBJECT, message)
        diagnostic = message.split("command output (redacted and bounded):\n", 1)[1]
        self.assertLessEqual(
            len(diagnostic.splitlines()), self.proof.MAX_DIAGNOSTIC_LINES
        )
        self.assertLessEqual(
            len(diagnostic.encode("utf-8")), self.proof.MAX_DIAGNOSTIC_BYTES
        )

    def test_cleanup_failures_are_fatal_without_a_primary_failure(self) -> None:
        failures = (
            lambda: subprocess.CompletedProcess(["docker"], 1, "cleanup rejected"),
            lambda: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(["docker"], timeout=1)
            ),
            lambda: (_ for _ in ()).throw(OSError("unsafe operating-system detail")),
        )
        for cleanup in failures:
            with self.subTest(cleanup=cleanup):
                with self.assertRaises(self.proof.ProofFailure):
                    self.proof.preserve_cleanup_failure(
                        cleanup,
                        environment={},
                        primary_failure_active=False,
                    )

    def test_cleanup_failure_does_not_replace_primary_and_is_safely_reported(self) -> None:
        secret = "cleanup-secret-that-must-not-appear"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaisesRegex(self.proof.ProofFailure, "primary proof failure"):
                try:
                    raise self.proof.ProofFailure("primary proof failure")
                finally:
                    self.proof.preserve_cleanup_failure(
                        lambda: subprocess.CompletedProcess(
                            ["docker"],
                            1,
                            f"cleanup explanation; credential={secret}; subject={self.proof.GREEN_SUBJECT}",
                        ),
                        environment={"CLEANUP_TOKEN": secret},
                        primary_failure_active=sys.exc_info()[0] is not None,
                    )
        diagnostic = stderr.getvalue()
        self.assertIn("secondary cleanup failure", diagnostic)
        self.assertIn("cleanup explanation", diagnostic)
        self.assertNotIn(secret, diagnostic)
        self.assertNotIn(self.proof.GREEN_SUBJECT, diagnostic)

    def test_mixed_timeout_preserves_primary_when_emergency_cleanup_fails(self) -> None:
        secret = "emergency-cleanup-secret"
        cleanup_failures = (
            lambda: subprocess.CompletedProcess(
                ["docker"],
                1,
                f"remove failed; credential={secret}; subject={self.proof.BLUE_SUBJECT}",
            ),
            lambda: (_ for _ in ()).throw(
                subprocess.TimeoutExpired(["docker", "rm"], timeout=1)
            ),
        )
        for emergency_cleanup in cleanup_failures:
            with self.subTest(emergency_cleanup=emergency_cleanup):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaisesRegex(
                        self.proof.ProofFailure,
                        "mixed-generation Notary unexpectedly kept serving",
                    ):
                        self.proof.raise_mixed_notary_timeout(
                            "bounded-mixed-notary",
                            subprocess.TimeoutExpired(
                                ["docker", "compose"], timeout=45
                            ),
                            environment={"EMERGENCY_TOKEN": secret},
                            emergency_cleanup=emergency_cleanup,
                        )
                diagnostic = stderr.getvalue()
                self.assertIn("secondary cleanup failure", diagnostic)
                self.assertNotIn(secret, diagnostic)
                self.assertNotIn(self.proof.BLUE_SUBJECT, diagnostic)

    def test_workflows_use_the_pinned_compiler_and_live_proof(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        candidate = (ROOT / ".github" / "workflows" / "release-candidate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("just registry-projects-runtime-check", ci)
        self.assertNotIn("just contract-generation-proof", ci)
        self.assertIn("just registry-projects-runtime-check", candidate)
        self.assertIn("just contract-generation-proof", candidate)

    def test_clean_checkout_journey_is_one_documented_target(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(
            justfile,
            r"up-generated:\n    just generate\n    just registry-projects-runtime-check\n    just up",
        )
        quick_start = readme.split("## Quick Start", 1)[1].split("```bash", 1)[1].split("```", 1)[0]
        self.assertIn("just up-generated", quick_start)
        self.assertNotIn("just contract-generation-proof", quick_start)


if __name__ == "__main__":
    unittest.main()
