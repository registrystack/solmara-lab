from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELAY = "ghcr.io/registrystack/relay@sha256:" + "1" * 64
EVIDENCE = "ghcr.io/registrystack/evidence@sha256:" + "2" * 64
MINT = "ghcr.io/registrystack/mint@sha256:" + "3" * 64
VOLUME_INIT = "busybox@sha256:" + "4" * 64
GATEWAY = "caddy@sha256:" + "5" * 64


def load_check_image_pins():
    spec = importlib.util.spec_from_file_location(
        "check_image_pins", ROOT / "scripts" / "check-image-pins.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load check-image-pins.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_image_pins"] = module
    spec.loader.exec_module(module)
    return module


class ImagePinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_check_image_pins()
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.module.ROOT = self.root
        (self.root / "versions.env").write_text(
            f"REGISTRY_RELAY_IMAGE={RELAY}\n"
            f"SOLMARA_EVIDENCE_IMAGE={EVIDENCE}\n"
            f"SOLMARA_MINT_IMAGE={MINT}\n"
            f"VOLUME_INIT_IMAGE={VOLUME_INIT}\n"
            f"EVIDENCE_GATEWAY_IMAGE={GATEWAY}\n",
            encoding="utf-8",
        )
        with (self.root / "versions.env").open("a", encoding="utf-8") as versions:
            for key in (
                "PYTHON_STATIC_IMAGE", "NODE_BUILD_IMAGE", "UV_BUILD_IMAGE",
                "ESIGNET_REDIS_IMAGE", "ESIGNET_BASE_IMAGE",
                "ESIGNET_UI_IMAGE", "ESIGNET_POSTGRES_IMAGE",
            ):
                versions.write(f"{key}=example.invalid/image@sha256:{'6' * 64}\n")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_check(self, *, required: bool = True) -> tuple[int, str]:
        operator = ":?required" if required else ":-fallback"
        (self.root / "compose.yaml").write_text(
            "services:\n"
            f"  relay:\n    image: ${{REGISTRY_RELAY_IMAGE{operator}}}\n"
            f"  evidence:\n    image: ${{SOLMARA_EVIDENCE_IMAGE{operator}}}\n"
            f"  mint:\n    image: ${{SOLMARA_MINT_IMAGE{operator}}}\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.module.main()
        return result, stderr.getvalue()

    def test_matching_source_image_references_pass(self) -> None:
        result, stderr = self.run_check()

        self.assertEqual(result, 0, stderr)

    def test_source_images_must_be_required(self) -> None:
        result, stderr = self.run_check(required=False)

        self.assertEqual(result, 1)
        self.assertIn("expected a required REGISTRY_RELAY_IMAGE reference", stderr)

    def test_gateway_must_be_digest_pinned(self) -> None:
        versions = (self.root / "versions.env").read_text().replace(GATEWAY, "caddy:latest")
        (self.root / "versions.env").write_text(versions)
        result, stderr = self.run_check()

        self.assertEqual(result, 1)
        self.assertIn("EVIDENCE_GATEWAY_IMAGE must use image@sha256", stderr)

    def test_runtime_images_must_use_their_exact_official_repository(self) -> None:
        versions = (self.root / "versions.env").read_text().replace(
            EVIDENCE,
            "ghcr.io/registrystack/solmara-lab-evidence@sha256:" + "2" * 64,
        )
        (self.root / "versions.env").write_text(versions)
        result, stderr = self.run_check()

        self.assertEqual(result, 1)
        self.assertIn(
            "SOLMARA_EVIDENCE_IMAGE must use "
            "ghcr.io/registrystack/evidence@sha256:",
            stderr,
        )

    def test_runtime_builder_only_builds_checksum_verified_relayctl(self) -> None:
        builder = (ROOT / "scripts" / "build-registry-stack-runtime.sh").read_text(
            encoding="utf-8"
        )
        dockerfile = (
            ROOT / "docker" / "registry-stack-release-binary" / "Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn('verify_official_runtime evidence "$evidence_image"', builder)
        self.assertIn('verify_official_runtime mint "$mint_image"', builder)
        self.assertIn('build_relayctl "$relayctl_image"', builder)
        self.assertNotIn("REGISTRY_STACK_RELEASE_EVIDENCE_ASSET", builder)
        self.assertNotIn("REGISTRY_STACK_RELEASE_MINT_ASSET", builder)
        self.assertIn("REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256", builder)
        self.assertIn("relayctl_sha256", builder)
        self.assertNotIn("wget", dockerfile)
        self.assertNotIn("curl", dockerfile)
        self.assertNotIn(" AS evidence", dockerfile)
        self.assertNotIn(" AS mint", dockerfile)

    def test_hosted_pin_gate_verifies_official_runtime_tag_digests_and_labels(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")

        self.assertIn("hosted-pin-check: build-runtime-images", justfile)

    def test_lint_excludes_the_exact_vendor_checkout_only(self) -> None:
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")

        self.assertIn("ruff check --select E4,E7,E9,F --exclude vendor .", justfile)


if __name__ == "__main__":
    unittest.main()
