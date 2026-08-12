from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "registry_stack_tool", PROJECT_ROOT / "scripts/registry-stack-tool.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load registry-stack-tool.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["registry_stack_tool"] = module
    spec.loader.exec_module(module)
    return module


class RegistryStackToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_tool()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.module.ROOT = self.root
        self.binary = b"#!/bin/sh\necho 'registryctl 0.18.0'\n"
        checksum = hashlib.sha256(self.binary).hexdigest()
        (self.root / "versions.env").write_text(
            "REGISTRYCTL_VERSION=0.18.0\n"
            f"REGISTRY_STACK_REGISTRYCTL_LINUX_AMD64_SHA256={checksum}\n",
            encoding="utf-8",
        )
        self.environment = mock.patch.dict(
            os.environ,
            {"SOLMARA_REGISTRY_STACK_CACHE": str(self.cache)},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.module.main(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_path_downloads_checksums_caches_and_verifies_the_host_binary(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [self.binary, b""]
        with (
            mock.patch.object(self.module.platform, "system", return_value="Linux"),
            mock.patch.object(self.module.platform, "machine", return_value="x86_64"),
            mock.patch.object(
                self.module.urllib.request, "urlopen", return_value=response
            ) as download,
        ):
            result, stdout, stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )
            cached_result, cached_stdout, cached_stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )

        self.assertEqual(result, 0, stderr)
        self.assertEqual(cached_result, 0, cached_stderr)
        self.assertEqual(stdout, cached_stdout)
        binary = Path(stdout.strip())
        self.assertEqual(binary.read_bytes(), self.binary)
        self.assertTrue(binary.stat().st_mode & 0o100)
        download.assert_called_once_with(
            "https://github.com/registrystack/registry-stack/releases/download/"
            "v0.18.0/registryctl-v0.18.0-linux-amd64",
            timeout=60,
        )

    def test_checksum_mismatch_is_rejected_without_populating_the_cache(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [b"wrong bytes", b""]
        with (
            mock.patch.object(self.module.platform, "system", return_value="Linux"),
            mock.patch.object(self.module.platform, "machine", return_value="amd64"),
            mock.patch.object(
                self.module.urllib.request, "urlopen", return_value=response
            ),
        ):
            result, stdout, stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )

        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("checksum mismatch", stderr)
        self.assertFalse(
            (self.cache / "v0.18.0/registryctl-v0.18.0-linux-amd64").exists()
        )

    def test_http_error_is_reported_without_a_traceback(self) -> None:
        error = urllib.error.HTTPError(
            "https://example.invalid/asset", 404, "Not Found", {}, io.BytesIO()
        )
        self.addCleanup(error.close)
        with (
            mock.patch.object(self.module.platform, "system", return_value="Linux"),
            mock.patch.object(self.module.platform, "machine", return_value="amd64"),
            mock.patch.object(
                self.module.urllib.request, "urlopen", side_effect=error
            ),
        ):
            result, stdout, stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )

        self.assertEqual(result, 1)
        self.assertEqual(stdout, "")
        self.assertIn("HTTP 404", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_path_rejects_a_checksum_valid_binary_with_the_wrong_version(self) -> None:
        wrong = b"#!/bin/sh\necho 'registryctl 0.17.0'\n"
        checksum = hashlib.sha256(wrong).hexdigest()
        (self.root / "versions.env").write_text(
            "REGISTRYCTL_VERSION=0.18.0\n"
            f"REGISTRY_STACK_REGISTRYCTL_LINUX_AMD64_SHA256={checksum}\n",
            encoding="utf-8",
        )
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [wrong, b""]
        with (
            mock.patch.object(self.module.platform, "system", return_value="Linux"),
            mock.patch.object(self.module.platform, "machine", return_value="amd64"),
            mock.patch.object(
                self.module.urllib.request, "urlopen", return_value=response
            ),
        ):
            result, _, stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )

        self.assertEqual(result, 1)
        self.assertIn("did not report registryctl 0.18.0", stderr)

    def test_asset_supports_a_cross_platform_checksum_verified_download(self) -> None:
        payload = b"linux arm64 release binary"
        checksum = hashlib.sha256(payload).hexdigest()
        with (self.root / "versions.env").open("a", encoding="utf-8") as versions:
            versions.write(
                f"REGISTRY_STACK_MINT_LINUX_ARM64_SHA256={checksum}\n"
            )
        response = mock.MagicMock()
        response.__enter__.return_value.read.side_effect = [payload, b""]
        with mock.patch.object(
            self.module.urllib.request, "urlopen", return_value=response
        ):
            result, stdout, stderr = self.run_main(
                ["registry-stack-tool.py", "asset", "mint", "linux-arm64"]
            )

        self.assertEqual(result, 0, stderr)
        self.assertEqual(Path(stdout.strip()).read_bytes(), payload)

    def test_unsupported_host_fails_before_download(self) -> None:
        with (
            mock.patch.object(self.module.platform, "system", return_value="Darwin"),
            mock.patch.object(self.module.platform, "machine", return_value="x86_64"),
            mock.patch.object(self.module.urllib.request, "urlopen") as download,
        ):
            result, _, stderr = self.run_main(
                ["registry-stack-tool.py", "path", "registryctl"]
            )

        self.assertEqual(result, 1)
        self.assertIn("unsupported host platform", stderr)
        download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
