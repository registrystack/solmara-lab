from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELAY = "solmara-lab-registry-relay:source"
EVIDENCE = "solmara-lab-registry-evidence:source"
MINT = "solmara-lab-registry-mint:source"
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


if __name__ == "__main__":
    unittest.main()
