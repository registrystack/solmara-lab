from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RELAY = "ghcr.io/registrystack/registry-relay@sha256:" + "1" * 64
NOTARY = "ghcr.io/registrystack/registry-notary@sha256:" + "2" * 64


def load_check_release_pins():
    spec = importlib.util.spec_from_file_location(
        "check_release_pins", ROOT / "scripts" / "check-release-pins.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load check-release-pins.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release_pins"] = module
    spec.loader.exec_module(module)
    return module


class ReleasePinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(os.environ, {})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("REGISTRY_RELAY_IMAGE", None)
        os.environ.pop("REGISTRY_NOTARY_IMAGE", None)

        self.module = load_check_release_pins()
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.module.ROOT = self.root
        (self.root / "versions.env").write_text(
            f"REGISTRY_RELAY_IMAGE={RELAY}\nREGISTRY_NOTARY_IMAGE={NOTARY}\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_matching_environment_overrides_validate_committed_pins(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {"REGISTRY_RELAY_IMAGE": RELAY, "REGISTRY_NOTARY_IMAGE": NOTARY},
                clear=True,
            ),
            mock.patch.object(
                self.module,
                "inspect_tag_digest",
                side_effect=["sha256:" + "1" * 64, "sha256:" + "2" * 64],
            ) as inspect,
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 0)

        self.assertEqual(inspect.call_count, 2)

    def test_temporary_versions_are_isolated_from_ambient_image_overrides(self) -> None:
        self.assertNotIn("REGISTRY_RELAY_IMAGE", os.environ)
        self.assertNotIn("REGISTRY_NOTARY_IMAGE", os.environ)

    def test_candidate_test_passes_with_workflow_image_environment(self) -> None:
        committed = self.module.read_versions(ROOT / "versions.env")
        environment = os.environ.copy()
        environment.update(
            {
                "REGISTRY_RELAY_IMAGE": committed["REGISTRY_RELAY_IMAGE"],
                "REGISTRY_NOTARY_IMAGE": committed["REGISTRY_NOTARY_IMAGE"],
            }
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "test_release_pins.ReleasePinTests."
                "test_candidate_prerelease_tag_is_accepted",
            ],
            cwd=ROOT / "scripts",
            env=environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_candidate_prerelease_tag_is_accepted(self) -> None:
        with mock.patch.object(
            self.module,
            "inspect_tag_digest",
            side_effect=["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        ):
            self.assertEqual(
                self.module.main(["check-release-pins.py", "v1.0.0-rc.1"]),
                0,
            )

    def test_mismatched_environment_override_fails_before_registry_lookup(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch.dict(
                os.environ,
                {"REGISTRY_RELAY_IMAGE": RELAY[:-1] + "3"},
                clear=True,
            ),
            mock.patch.object(self.module, "inspect_tag_digest") as inspect,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 1)

        self.assertEqual(inspect.call_count, 0)
        self.assertIn(
            "REGISTRY_RELAY_IMAGE environment override must match versions.env",
            stderr.getvalue(),
        )

    def test_malicious_tags_are_rejected_before_registry_lookup(self) -> None:
        malicious_tags = (
            "v1.0.0; echo INJECTED",
            "v1.0.0 rc.1",
            "v1.0.0'quoted",
            'v1.0.0"quoted',
            "v1.0.0$(echo INJECTED)",
            "v1.0.0\necho INJECTED",
        )
        for tag in malicious_tags:
            with self.subTest(tag=tag):
                stderr = io.StringIO()
                with (
                    mock.patch.object(self.module, "inspect_tag_digest") as inspect,
                    contextlib.redirect_stderr(stderr),
                ):
                    result = self.module.main(["check-release-pins.py", tag])

                self.assertEqual(result, 2)
                inspect.assert_not_called()
                self.assertIn("tag must match", stderr.getvalue())

    def test_release_recipe_dry_runs_do_not_interpolate_tag(self) -> None:
        malicious_tags = (
            "v1.0.0; echo INJECTED",
            "v1.0.0 rc.1",
            "v1.0.0'quoted",
            'v1.0.0"quoted',
            "v1.0.0$(echo INJECTED)",
            "v1.0.0\necho INJECTED",
        )
        recipes = {
            "release-pins": 'scripts/check-release-pins.py "$1"',
            "review-release": (
                'scripts/check-release-pins.py "$1"\nscripts/review.sh'
            ),
        }
        for recipe, expected in recipes.items():
            for tag in malicious_tags:
                with self.subTest(recipe=recipe, tag=tag):
                    result = subprocess.run(
                        ["just", "--dry-run", recipe, tag],
                        cwd=ROOT,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stderr.strip(), expected)

    def test_review_release_recipe_requires_tag(self) -> None:
        result = subprocess.run(
            ["just", "--dry-run", "review-release"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("takes 1", result.stderr)


if __name__ == "__main__":
    unittest.main()
