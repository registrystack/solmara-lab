from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hosted-runtime-assets.py"
SPEC = importlib.util.spec_from_file_location("hosted_runtime_assets", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PROVISIONER_SCRIPT = ROOT / "scripts" / "provision-hosted-runtime.py"
PROVISIONER_SPEC = importlib.util.spec_from_file_location(
    "provision_hosted_runtime", PROVISIONER_SCRIPT
)
assert PROVISIONER_SPEC and PROVISIONER_SPEC.loader
PROVISIONER = importlib.util.module_from_spec(PROVISIONER_SPEC)
PROVISIONER_SPEC.loader.exec_module(PROVISIONER)


class HostedRuntimeAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "source"
        self.root.mkdir()
        self._copy_inventory(
            ROOT / "generator" / "solmara_lab",
            self.root / "generator" / "solmara_lab",
            MODULE.GENERATOR_FILES,
        )
        for authority in MODULE.AUTHORITIES:
            self._copy_inventory(
                ROOT / "relays" / authority,
                self.root / "relays" / authority,
                MODULE.RELAY_FILES[authority],
            )
        for cell in MODULE.EVIDENCE_CELLS:
            self._copy_inventory(
                ROOT / "evidence" / "cells" / cell,
                self.root / "evidence" / "cells" / cell,
                MODULE.EVIDENCE_FILES[cell],
            )
        mint = self.root / "evidence" / "mint.yaml"
        mint.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "evidence" / "mint.yaml", mint)
        self.relayctl = Path(self.temporary.name) / "relayctl"
        self.relayctl.write_text(
            """#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import sys

if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit(3)
project = pathlib.Path(sys.argv[sys.argv.index("package") + 1])
output = pathlib.Path(sys.argv[sys.argv.index("--output") + 1])
runtime = (project / "runtime.yaml").read_text()
if "path: source.sqlite" not in runtime or not (project / "source.sqlite").is_file():
    raise SystemExit(4)
digest = hashlib.sha256()
for path in sorted(project.rglob("*")):
    if path.is_file():
        digest.update(path.relative_to(project).as_posix().encode())
        digest.update(path.read_bytes())
output.mkdir(parents=True)
(output / "relay-package.json").write_text(
    json.dumps({"projectDigest": digest.hexdigest()}, sort_keys=True) + "\\n"
)
""",
            encoding="utf-8",
        )
        self.relayctl.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _copy_inventory(source: Path, destination: Path, files: frozenset[str]) -> None:
        for relative in files:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)

    @staticmethod
    def _digests(root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = MODULE._digest(path)
        return result

    def _assert_no_path_leakage(self, root: Path) -> None:
        forbidden = (
            str(self.root).encode(),
            str(root).encode(),
            str(Path(self.temporary.name)).encode(),
            b"solmara-hosted-assets-",
        )
        for path in root.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                for value in forbidden:
                    self.assertNotIn(value, content, path)

    def test_build_contains_only_closed_runtime_assets(self) -> None:
        output = Path(self.temporary.name) / "assets"
        MODULE.build(self.root, output, self.relayctl)
        MODULE.verify_manifest(output)

        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        files = set(manifest["files"])
        expected_files = set()
        for authority in MODULE.AUTHORITIES:
            prefix = f"relays/{authority}"
            expected_files.update(
                {
                    f"{prefix}/runtime.yaml",
                    f"{prefix}/package/relay-package.json",
                    f"{prefix}/source/{authority}.sqlite",
                }
            )
        for cell in MODULE.EVIDENCE_CELLS:
            expected_files.update(
                f"evidence/cells/{cell}/{relative}"
                for relative in MODULE.EVIDENCE_FILES[cell]
            )
        expected_files.add("mint/mint.yaml")
        expected_files.update(
            f"generator/solmara_lab/{relative}" for relative in MODULE.GENERATOR_FILES
        )
        self.assertEqual(files, expected_files)
        self.assertFalse(any(path.endswith(".pyc") for path in files))
        self.assertFalse(any("/secrets/" in f"/{path}/" for path in files))
        self._assert_no_path_leakage(output)

    def test_unexpected_secret_symlink_and_bytecode_are_refused(self) -> None:
        injections = (
            ("relays/cra/unexpected.yaml", b"UNEXPECTED-CANARY"),
            ("evidence/cells/cra/bundle/signing.jwk", b"PRIVATE-JWK-CANARY"),
            ("evidence/cells/nia/bundle/audit/events.jsonl", b"AUDIT-CANARY"),
            ("evidence/cells/sro/bundle/extracts/source.sqlite", b"EXTRACT-CANARY"),
            ("generator/solmara_lab/__pycache__/publisher.pyc", b"PYC-CANARY"),
        )
        for relative, content in injections:
            with self.subTest(relative=relative):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                with self.assertRaisesRegex(MODULE.AssetBuildError, "inventory"):
                    MODULE._validate_sources(self.root)
                path.unlink()
                for parent in path.parents:
                    if parent == self.root or any(parent.iterdir()):
                        break
                    parent.rmdir()

        link = self.root / "evidence" / "cells" / "sro" / "bundle" / "linked.yaml"
        link.symlink_to(self.root / "evidence" / "mint.yaml")
        with self.assertRaisesRegex(MODULE.AssetBuildError, "symbolic link"):
            MODULE._validate_sources(self.root)

    def test_manifest_refuses_tampering_extra_files_and_noncanonical_bytes(
        self,
    ) -> None:
        output = Path(self.temporary.name) / "assets"
        MODULE.build(self.root, output, self.relayctl)
        PROVISIONER.verify_assets(output)
        target = output / "mint" / "mint.yaml"
        original = target.read_bytes()
        target.write_bytes(original + b"# tampered\n")
        with self.assertRaisesRegex(MODULE.AssetBuildError, "verification"):
            MODULE.verify_manifest(output)
        with self.assertRaisesRegex(PROVISIONER.ProvisionError, "invalid assets"):
            PROVISIONER.verify_assets(output)
        target.write_bytes(original)

        extra = output / "unexpected.txt"
        extra.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.AssetBuildError, "verification"):
            MODULE.verify_manifest(output)
        with self.assertRaisesRegex(PROVISIONER.ProvisionError, "invalid assets"):
            PROVISIONER.verify_assets(output)
        extra.unlink()

        manifest = output / "manifest.json"
        canonical = manifest.read_text(encoding="utf-8")
        manifest.write_text(json.dumps(json.loads(canonical)) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.AssetBuildError, "verification"):
            MODULE.verify_manifest(output)
        with self.assertRaisesRegex(PROVISIONER.ProvisionError, "invalid assets"):
            PROVISIONER.verify_assets(output)

    def test_two_builds_are_byte_for_byte_deterministic(self) -> None:
        first = Path(self.temporary.name) / "first"
        second = Path(self.temporary.name) / "second"
        MODULE.build(self.root, first, self.relayctl)
        MODULE.build(self.root, second, self.relayctl)
        self.assertEqual(self._digests(first), self._digests(second))

    def test_relayctl_failure_is_redacted_and_leaves_no_output(self) -> None:
        canary = "RELAYCTL-PRIVATE-CANARY"
        failing = Path(self.temporary.name) / "failing-relayctl"
        failing.write_text(
            f"#!/bin/sh\nprintf '%s\\n' '{canary}'\nprintf '%s\\n' '{canary}' >&2\nexit 19\n",
            encoding="utf-8",
        )
        failing.chmod(0o755)
        output = Path(self.temporary.name) / "failed-assets"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "build",
                "--root",
                str(self.root),
                "--output",
                str(output),
                "--relayctl",
                str(failing),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr.strip(), "hosted runtime asset build failed")
        combined = completed.stdout + completed.stderr
        for forbidden in (canary, str(self.root), str(output), str(failing)):
            self.assertNotIn(forbidden, combined)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
