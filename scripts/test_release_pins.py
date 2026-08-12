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
        checksums = "".join(
            f"REGISTRY_STACK_{tool}_{platform}_SHA256={'3' * 64}\n"
            for tool in ("EVIDENCE", "EVIDENCECTL", "MINT", "REGISTRYCTL")
            for platform in ("LINUX_AMD64", "LINUX_ARM64", "MACOS_ARM64")
        )
        (self.root / "versions.env").write_text(
            f"REGISTRY_RELAY_IMAGE={RELAY}\n"
            "REGISTRYCTL_VERSION=1.0.0\n"
            "REGISTRY_STACK_SOURCE_REF=v1.0.0\n"
            f"REGISTRY_STACK_SOURCE_COMMIT={'a' * 40}\n"
            + checksums,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_matching_environment_overrides_validate_committed_pins(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {"REGISTRY_RELAY_IMAGE": RELAY},
                clear=True,
            ),
            mock.patch.object(
                self.module,
                "inspect_tag_digest",
                return_value="sha256:" + "1" * 64,
            ) as inspect,
        ):
            self.assertEqual(self.module.main(["check-release-pins.py", "v1.0.0"]), 0)

        inspect.assert_called_once_with("ghcr.io/registrystack/registry-relay:v1.0.0")

    def test_temporary_versions_are_isolated_from_ambient_image_overrides(self) -> None:
        self.assertNotIn("REGISTRY_RELAY_IMAGE", os.environ)

    def test_candidate_test_passes_with_workflow_image_environment(self) -> None:
        committed = self.module.read_versions(ROOT / "versions.env")
        environment = os.environ.copy()
        environment.update(
            {
                "REGISTRY_RELAY_IMAGE": committed["REGISTRY_RELAY_IMAGE"],
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
            return_value="sha256:" + "1" * 64,
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

    def test_source_ref_must_match_the_release(self) -> None:
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                "REGISTRY_STACK_SOURCE_REF=v1.0.0",
                "REGISTRY_STACK_SOURCE_REF=v0.13.0",
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

    def test_release_artifact_checksum_closure_is_required(self) -> None:
        versions = (self.root / "versions.env").read_text(encoding="utf-8")
        (self.root / "versions.env").write_text(
            versions.replace(
                f"REGISTRY_STACK_MINT_LINUX_AMD64_SHA256={'3' * 64}",
                "REGISTRY_STACK_MINT_LINUX_AMD64_SHA256=missing",
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
        self.assertIn("REGISTRY_STACK_MINT_LINUX_AMD64_SHA256", stderr.getvalue())

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

if __name__ == "__main__":
    unittest.main()
