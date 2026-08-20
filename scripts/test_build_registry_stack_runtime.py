from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build-registry-stack-runtime.sh"


class RegistryStackRuntimeBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        scripts = self.root / "scripts"
        binaries = self.root / "bin"
        scripts.mkdir()
        binaries.mkdir()
        shutil.copy2(BUILDER, scripts / BUILDER.name)

        release_check = scripts / "check-registry-stack-release-pin.py"
        release_check.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        release_check.chmod(0o755)

        self.digests = {
            "RELAY": "1" * 64,
            "EVIDENCE": "2" * 64,
            "MINT": "3" * 64,
        }
        self.relayctl_asset = self.root / "relayctl-release-asset"
        self.relayctl_asset.write_bytes(b"published relayctl fixture")
        relayctl_sha256 = hashlib.sha256(self.relayctl_asset.read_bytes()).hexdigest()
        (self.root / "versions.env").write_text(
            "REGISTRY_STACK_REQUIRED_VERSION=0.23.0\n"
            "REGISTRY_STACK_SOURCE_COMMIT=" + "a" * 40 + "\n"
            f"REGISTRY_STACK_RELEASE_RELAY_DIGEST={self.digests['RELAY']}\n"
            f"REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/relay@sha256:{self.digests['RELAY']}\n"
            f"SOLMARA_EVIDENCE_IMAGE=ghcr.io/registrystack/evidence@sha256:{self.digests['EVIDENCE']}\n"
            f"SOLMARA_MINT_IMAGE=ghcr.io/registrystack/mint@sha256:{self.digests['MINT']}\n"
            "REGISTRY_RELAYCTL_IMAGE=solmara-lab-relayctl:v0.23.0\n"
            "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL=https://example.invalid/relayctl\n"
            f"REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256={relayctl_sha256}\n",
            encoding="utf-8",
        )

        self.log = self.root / "docker.log"
        docker = binaries / "docker"
        docker.write_text(
            """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
with Path(os.environ["FAKE_DOCKER_LOG"]).open("a", encoding="utf-8") as log:
    log.write(" ".join(arguments) + "\\n")

if arguments[:3] == ["buildx", "imagetools", "inspect"]:
    component = arguments[3].split("/")[-1].split(":", 1)[0].upper()
    print(os.environ[f"TAG_DIGEST_{component}"])
elif arguments[:2] == ["image", "inspect"]:
    if os.environ.get("FORCE_RELAYCTL_BUILD") == "1" and arguments[-1].startswith("solmara-lab-relayctl:"):
        raise SystemExit(0)
    output_format = arguments[arguments.index("--format") + 1]
    if ".Architecture" in output_format:
        print("amd64")
    elif "org.opencontainers.image.revision" in output_format:
        print("a" * 40)
    elif "org.opencontainers.image.version" in output_format:
        print("0.23.0")
    elif "org.opencontainers.image.source" in output_format:
        print("https://github.com/registrystack/registry-stack")
elif arguments[0] == "pull":
    pass
elif arguments[:2] == ["buildx", "build"]:
    if os.environ.get("FORCE_RELAYCTL_BUILD") != "1":
        raise SystemExit("relayctl should have been satisfied by the cached image")
else:
    raise SystemExit(f"unexpected docker invocation: {arguments}")
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        curl = binaries / "curl"
        curl.write_text(
            """#!/usr/bin/env python3
import os
import shutil
import sys

if os.environ.get("FAIL_IF_CURL") == "1":
    raise SystemExit("curl must not run when a verified asset file is supplied")
arguments = sys.argv[1:]
output = arguments[arguments.index("--output") + 1]
shutil.copyfile(os.environ["FAKE_RELAYCTL_SOURCE"], output)
""",
            encoding="utf-8",
        )
        curl.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": f"{binaries}:{os.environ['PATH']}",
            "FAKE_DOCKER_LOG": str(self.log),
            "FAKE_RELAYCTL_SOURCE": str(self.relayctl_asset),
            **{
                f"TAG_DIGEST_{component}": f"sha256:{digest}"
                for component, digest in self.digests.items()
            },
        }
        self.environment.pop("REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_FILE", None)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def run_builder(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(self.root / "scripts" / BUILDER.name)],
            cwd=self.root,
            env=self.environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_all_official_version_tags_match_their_pinned_digests(self) -> None:
        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        for component in ("relay", "evidence", "mint"):
            self.assertIn(
                f"buildx imagetools inspect ghcr.io/registrystack/{component}:v0.23.0",
                calls,
            )

    def test_mismatched_official_tag_digest_fails_closed(self) -> None:
        self.environment["TAG_DIGEST_EVIDENCE"] = "sha256:" + "9" * 64

        result = self.run_builder()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "published evidence tag does not match the pinned digest",
            result.stderr,
        )
        calls = self.log.read_text(encoding="utf-8")
        self.assertNotIn("ghcr.io/registrystack/mint:v0.23.0", calls)

    def test_relayctl_is_verified_on_the_host_before_the_minimal_image_build(self) -> None:
        self.environment["FORCE_RELAYCTL_BUILD"] = "1"

        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertIn("buildx build --load --platform linux/amd64", calls)
        self.assertIn("--target relayctl", calls)
        self.assertNotIn("REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL", calls)
        self.assertNotIn("REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256", calls)

    def test_preverified_relayctl_file_avoids_a_second_network_download(self) -> None:
        self.environment["FORCE_RELAYCTL_BUILD"] = "1"
        self.environment["FAIL_IF_CURL"] = "1"
        self.environment["REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_FILE"] = str(
            self.relayctl_asset
        )

        result = self.run_builder()

        self.assertEqual(result.returncode, 0, result.stderr)
