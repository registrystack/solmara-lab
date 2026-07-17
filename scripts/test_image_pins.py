from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELAY = "ghcr.io/registrystack/registry-relay@sha256:" + "1" * 64
NOTARY = "ghcr.io/registrystack/registry-notary@sha256:" + "2" * 64


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
            f"REGISTRY_RELAY_IMAGE={RELAY}\nREGISTRY_NOTARY_IMAGE={NOTARY}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_check(self, relay: str = RELAY, notary: str = NOTARY) -> tuple[int, str]:
        (self.root / "compose.yaml").write_text(
            "services:\n"
            f"  relay:\n    image: ${{REGISTRY_RELAY_IMAGE:-{relay}}}\n"
            f"  notary:\n    image: ${{REGISTRY_NOTARY_IMAGE:-{notary}}}\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.module.main()
        return result, stderr.getvalue()

    def test_matching_compose_fallbacks_pass(self) -> None:
        result, stderr = self.run_check()

        self.assertEqual(result, 0, stderr)

    def test_relay_fallback_must_match_versions_env(self) -> None:
        result, stderr = self.run_check(relay=RELAY[:-1] + "3")

        self.assertEqual(result, 1)
        self.assertIn("REGISTRY_RELAY_IMAGE fallback must match versions.env", stderr)

    def test_notary_fallback_must_match_versions_env(self) -> None:
        result, stderr = self.run_check(notary=NOTARY[:-1] + "3")

        self.assertEqual(result, 1)
        self.assertIn("REGISTRY_NOTARY_IMAGE fallback must match versions.env", stderr)


if __name__ == "__main__":
    unittest.main()
