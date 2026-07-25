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
        self.resolve_tag_implementation = self.module.resolve_tag_commit
        self.resolve_tag = mock.patch.object(
            self.module,
            "resolve_tag_commit",
            return_value="a" * 40,
        )
        self.resolve_tag.start()
        self.addCleanup(self.resolve_tag.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.module.ROOT = self.root
        (self.root / "versions.env").write_text(
            f"REGISTRY_RELAY_IMAGE={RELAY}\n"
            f"REGISTRY_NOTARY_IMAGE={NOTARY}\n"
            "REGISTRYCTL_VERSION=1.0.0\n"
            "REGISTRY_STACK_SOURCE_REF=v1.0.0\n"
            f"REGISTRY_STACK_SOURCE_COMMIT={'a' * 40}\n"
            "REGISTRY_RELAY_FEATURES=attribute-release\n"
            f"SOLMARA_RELAY_RUNTIME_IMAGE="
            f"{self.module.SOLMARA_RELAY_RUNTIME_REPOSITORY}"
            f"@sha256:{'3' * 64}\n",
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
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                "REGISTRYCTL_VERSION=1.0.0",
                "REGISTRYCTL_VERSION=1.0.0-rc.1",
            ),
            encoding="utf-8",
        )
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                "REGISTRY_STACK_SOURCE_REF=v1.0.0",
                "REGISTRY_STACK_SOURCE_REF=v1.0.0-rc.1",
            ),
            encoding="utf-8",
        )
        with mock.patch.object(
            self.module,
            "inspect_tag_digest",
            side_effect=["sha256:" + "1" * 64, "sha256:" + "2" * 64],
        ):
            self.assertEqual(
                self.module.main(["check-release-pins.py", "v1.0.0-rc.1"]),
                0,
            )

    def test_registryctl_version_must_match_release_tag(self) -> None:
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                "REGISTRYCTL_VERSION=1.0.0",
                "REGISTRYCTL_VERSION=0.13.0",
            ),
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(self.module, "inspect_tag_digest") as inspect,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 1)

        inspect.assert_not_called()
        self.assertIn(
            "REGISTRYCTL_VERSION from versions.env is 0.13.0, expected 1.0.0",
            stderr.getvalue(),
        )

    def test_source_commit_must_match_resolved_release_tag(self) -> None:
        self.module.resolve_tag_commit.return_value = "b" * 40
        stderr = io.StringIO()
        with (
            mock.patch.object(self.module, "inspect_tag_digest") as inspect,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 1)

        inspect.assert_not_called()
        self.assertIn(
            f"REGISTRY_STACK_SOURCE_COMMIT from versions.env is {'a' * 40}",
            stderr.getvalue(),
        )
        self.assertIn(
            f"v1.0.0 resolves to {'b' * 40}",
            stderr.getvalue(),
        )

    def test_resolve_tag_commit_prefers_the_peeled_annotated_tag(self) -> None:
        direct = "1" * 40
        peeled = "2" * 40
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                f"{direct}\trefs/tags/v1.0.0\n"
                f"{peeled}\trefs/tags/v1.0.0^{{}}\n"
            ),
            stderr="",
        )
        with mock.patch.object(self.module.subprocess, "run", return_value=completed):
            self.assertEqual(
                self.resolve_tag_implementation("v1.0.0"),
                peeled,
            )

    def test_resolve_tag_commit_accepts_a_lightweight_tag(self) -> None:
        direct = "3" * 40
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=f"{direct}\trefs/tags/v1.0.0\n",
            stderr="",
        )
        with mock.patch.object(self.module.subprocess, "run", return_value=completed):
            self.assertEqual(
                self.resolve_tag_implementation("v1.0.0"),
                direct,
            )

    def test_relay_source_ref_and_feature_must_match_the_release(self) -> None:
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                "REGISTRY_STACK_SOURCE_REF=v1.0.0",
                "REGISTRY_STACK_SOURCE_REF=v0.13.0",
            ).replace(
                "REGISTRY_RELAY_FEATURES=attribute-release",
                "REGISTRY_RELAY_FEATURES=ogcapi-features",
            ),
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(self.module, "inspect_tag_digest") as inspect,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 1)

        inspect.assert_not_called()
        self.assertIn(
            "REGISTRY_STACK_SOURCE_REF from versions.env is v0.13.0, expected v1.0.0",
            stderr.getvalue(),
        )
        self.assertIn(
            "REGISTRY_RELAY_FEATURES must include attribute-release",
            stderr.getvalue(),
        )

    def test_relay_runtime_must_be_published_and_digest_pinned(self) -> None:
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                (
                    f"{self.module.SOLMARA_RELAY_RUNTIME_REPOSITORY}"
                    f"@sha256:{'3' * 64}"
                ),
                "solmara-lab-registry-relay:local",
            ),
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(self.module, "inspect_tag_digest") as inspect,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 1)

        inspect.assert_not_called()
        self.module.resolve_tag_commit.assert_not_called()
        self.assertIn(
            "SOLMARA_RELAY_RUNTIME_IMAGE must pin "
            f"{self.module.SOLMARA_RELAY_RUNTIME_REPOSITORY}@sha256:<digest>",
            stderr.getvalue(),
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
