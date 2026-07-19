from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
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
