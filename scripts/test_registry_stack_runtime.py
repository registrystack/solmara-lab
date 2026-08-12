from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RegistryStackRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "scripts/build-registry-stack-runtime.sh",
            self.root / "scripts/build-registry-stack-runtime.sh",
        )
        shutil.copy2(PROJECT_ROOT / "versions.env", self.root / "versions.env")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "docker.log"

        downloader = self.root / "scripts/registry-stack-tool.py"
        downloader.write_text(
            "#!/bin/sh\n"
            "case \"$2\" in\n"
            "  evidence) echo \"$FAKE_ASSET_ROOT/evidence\" ;;\n"
            "  mint) echo \"$FAKE_ASSET_ROOT/mint\" ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        downloader.chmod(0o755)
        for name in ("evidence", "mint"):
            (self.root / name).write_bytes(name.encode("utf-8"))

        docker = self.bin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
            "case \"$1 $2\" in\n"
            "  'image inspect') exit 1 ;;\n"
            "  'buildx build') exit 0 ;;\n"
            "esac\n"
            "case \"$1:$*\" in\n"
            "  run:*registry-evidence*) echo 'evidence 0.18.0' ;;\n"
            "  run:*registry-mint*) echo 'mint 0.18.0' ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def test_builds_release_binary_images_and_only_consumes_relay_by_digest(self) -> None:
        environment = os.environ.copy()
        environment.update(
            {
                "FAKE_ASSET_ROOT": str(self.root),
                "FAKE_DOCKER_LOG": str(self.log),
                "PATH": f"{self.bin}:{environment['PATH']}",
                "REGISTRY_STACK_PLATFORM": "linux/amd64",
            }
        )
        result = subprocess.run(
            ["sh", self.root / "scripts/build-registry-stack-runtime.sh"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("buildx build"), 2)
        self.assertEqual(calls.count("run --rm"), 2)
        self.assertNotIn("registry-relay --version", calls)
        self.assertIn(
            "Relay uses ghcr.io/registrystack/registry-relay@sha256:",
            result.stdout,
        )

    def test_runtime_dockerfile_contains_no_source_build(self) -> None:
        dockerfile = (
            PROJECT_ROOT / "docker/registry-stack-runtime/Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertNotIn("cargo", dockerfile)
        self.assertNotIn("COPY . .", dockerfile)
        self.assertIn("COPY --chmod=0755 evidence", dockerfile)
        self.assertIn("COPY --chmod=0755 mint", dockerfile)


if __name__ == "__main__":
    unittest.main()
