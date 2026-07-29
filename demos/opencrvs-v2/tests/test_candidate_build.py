import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "demos" / "opencrvs-v2" / "build-candidate.sh"


class CandidateBuildContractTests(unittest.TestCase):
    def test_builder_is_fail_fast_and_uses_the_locked_monorepo(self) -> None:
        text = SCRIPT.read_text()

        self.assertIn("set -euo pipefail", text)
        self.assertIn("cargo build --release --locked", text)
        self.assertIn("release/docker/Dockerfile.registry-relay", text)
        self.assertNotIn("crates/registry-relay/scripts/build-image.sh", text)

    def test_builder_closes_candidate_provenance(self) -> None:
        text = SCRIPT.read_text()

        self.assertIn('git -C "${stack_dir}" status --porcelain', text)
        self.assertIn("org.opencontainers.image.revision=${commit}", text)
        self.assertIn(
            "org.registrystack.registry-relay.features=${relay_features}", text
        )
        self.assertIn("image_architecture", text)
        self.assertIn("image_revision", text)
        self.assertIn("image_features", text)
        self.assertIn("docker version --format '{{.Server.Arch}}'", text)
        self.assertIn("OPENCRVS_DEMO_RELAY_PLATFORM", text)


if __name__ == "__main__":
    unittest.main()
