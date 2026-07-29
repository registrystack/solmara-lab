from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_hosted_relay_bundles",
        ROOT / "scripts" / "check-hosted-relay-bundles.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load check-hosted-relay-bundles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_hosted_relay_bundles"] = module
    spec.loader.exec_module(module)
    return module


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_hosted_relay_bundles",
        ROOT / "scripts" / "generate-hosted-relay-bundles.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generate-hosted-relay-bundles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_hosted_relay_bundles"] = module
    spec.loader.exec_module(module)
    return module


class HostedRelayBundleTests(unittest.TestCase):
    def test_expected_bundle_sequence_comes_from_versions_file(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            checker.ROOT = Path(temporary_directory)
            (checker.ROOT / "versions.env").write_text(
                "SOLMARA_RELAY_BUNDLE_SEQUENCE=7\n",
                encoding="utf-8",
            )

            self.assertEqual(checker.expected_bundle_sequence(), 7)

    def test_expected_bundle_sequence_must_be_positive(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            checker.ROOT = Path(temporary_directory)
            (checker.ROOT / "versions.env").write_text(
                "SOLMARA_RELAY_BUNDLE_SEQUENCE=0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "must be a positive integer"):
                checker.expected_bundle_sequence()

    def test_generator_uses_the_same_configured_bundle_sequence(self) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            generator.ROOT = Path(temporary_directory)
            (generator.ROOT / "versions.env").write_text(
                "SOLMARA_RELAY_BUNDLE_SEQUENCE=7\n",
                encoding="utf-8",
            )

            self.assertEqual(generator.configured_bundle_sequence(), 7)

    def test_generator_accepts_a_1password_private_jwk_reference(self) -> None:
        generator = load_generator()
        reference = "op://vault-id/item-id/private_jwk"
        self.assertEqual(
            generator.validate_private_jwk_reference(reference),
            reference,
        )

    def test_generator_rejects_an_empty_1password_private_jwk_reference(self) -> None:
        generator = load_generator()
        with self.assertRaisesRegex(
            SystemExit,
            "invalid 1Password private JWK reference",
        ):
            generator.validate_private_jwk_reference("op://")

    def test_generator_rejects_private_material_in_the_public_jwk(self) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            public_jwk = Path(temporary_directory) / "public.jwk"
            public_jwk.write_text('{"kty":"OKP","d":"private"}\n', encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "expected a public-only JWK"):
                generator.validate_public_jwk(public_jwk)

    def test_public_and_consultation_bundle_variants_are_explicit(self) -> None:
        generator = load_generator()
        checker = load_checker()
        expected = (
            ("public", "relay.yaml", "", False),
            ("consultation", "relay-consultation.yaml", "consultation", True),
        )
        self.assertEqual(generator.BUNDLE_VARIANTS, expected)
        self.assertEqual(checker.BUNDLE_VARIANTS, expected)

    def test_governed_config_uses_variant_specific_trust_paths(self) -> None:
        generator = load_generator()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "relay-consultation.yaml"
            destination = root / "relay.yaml"
            source.write_text(
                "instance:\n  id: example-relay-consultation\nconsultation: {}\n",
                encoding="utf-8",
            )
            container_dir = (
                generator.CONTAINER_ROOT / "example" / "consultation"
            )
            generator.write_governed_config(
                source,
                destination,
                container_dir,
            )
            governed = yaml.safe_load(destination.read_text(encoding="utf-8"))
            self.assertEqual(
                governed["config_trust"],
                {
                    "trust_anchor_path": str(container_dir / "trust-anchor.json"),
                    "bundle_path": str(container_dir / "bundle"),
                    "antirollback_state_path": generator.ANTIROLLBACK_PATH,
                },
            )

    def test_artifact_closure_accepts_identical_complete_trees(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundled = root / "bundled"
            source = root / "source"
            for directory in (bundled, source):
                (directory / "contracts").mkdir(parents=True)
                (directory / "contracts" / "contract.json").write_text(
                    '{"version":1}\n', encoding="utf-8"
                )

            checker.verify_artifact_closure("example", bundled, source)

    def test_artifact_closure_rejects_changed_or_missing_files(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundled = root / "bundled"
            source = root / "source"
            bundled.mkdir()
            source.mkdir()
            (bundled / "contract.json").write_text("signed", encoding="utf-8")
            (source / "contract.json").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(
                SystemExit, "signed artifact contract.json differs"
            ):
                checker.verify_artifact_closure("example", bundled, source)

            (source / "extra.json").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "artifact paths differ"):
                checker.verify_artifact_closure("example", bundled, source)


if __name__ == "__main__":
    unittest.main()
