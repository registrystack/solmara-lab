from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

SCRIPT = Path(__file__).with_name("local-relay-runtime-stager.py")
SPEC = importlib.util.spec_from_file_location("local_relay_runtime_stager", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
ROOT = SCRIPT.parents[1]
AUTHORITIES = ("cra", "nia", "mosd", "sipf", "nagdi")


def isolated_source(root: Path, authority: str) -> Path:
    source = root / "source"
    source.mkdir(parents=True)
    shutil.copy2(ROOT / "relays" / authority / "runtime.yaml", source / "runtime.yaml")
    shutil.copytree(ROOT / "relays" / authority / "package", source / "package")
    return source


class LocalRelayRuntimeStagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = isolated_source(self.root, "cra")
        self.destination = self.root / "destination"
        self.destination.mkdir()
        self.uid = os.getuid()
        self.gid = os.getgid()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def stage(self) -> None:
        MODULE.stage(
            "cra",
            self.source,
            self.destination,
            target_uid=self.uid,
            target_gid=self.gid,
        )

    def test_stages_complete_package_and_preserves_matching_existing_volume(
        self,
    ) -> None:
        self.stage()

        self.assertEqual(
            {entry.name for entry in self.destination.iterdir()},
            {MODULE.LOCK_NAME, "runtime.yaml", "package"},
        )
        self.assertEqual(
            (self.destination / "runtime.yaml").read_bytes(),
            (self.source / "runtime.yaml").read_bytes(),
        )
        source_files = {
            path.relative_to(self.source / "package")
            for path in (self.source / "package").rglob("*")
            if path.is_file()
        }
        staged_files = {
            path.relative_to(self.destination / "package")
            for path in (self.destination / "package").rglob("*")
            if path.is_file()
        }
        self.assertEqual(staged_files, source_files)
        for path in (self.destination / "package").rglob("*"):
            metadata = path.stat()
            self.assertEqual((metadata.st_uid, metadata.st_gid), (self.uid, self.gid))
            self.assertEqual(
                stat.S_IMODE(metadata.st_mode), 0o500 if path.is_dir() else 0o400
            )

        first_inode = (self.destination / "package").stat().st_ino
        self.stage()
        self.assertEqual((self.destination / "package").stat().st_ino, first_inode)
        self.assertFalse((self.destination / MODULE.STAGING_PACKAGE).exists())
        self.assertFalse((self.destination / MODULE.STAGING_RUNTIME).exists())

        (self.source / "runtime.yaml").write_bytes(
            (self.source / "runtime.yaml").read_bytes() + b"\n"
        )
        with self.assertRaisesRegex(MODULE.StagingError, MODULE.FAILURE_MESSAGE):
            self.stage()
        self.assertEqual((self.destination / "package").stat().st_ino, first_inode)

    def test_source_inventory_rejects_links_unsafe_modes_and_extra_entries(
        self,
    ) -> None:
        attacks = []

        extra_source = isolated_source(self.root / "extra", "cra")
        (extra_source / "unexpected").write_text("value", encoding="utf-8")
        attacks.append(extra_source)

        symlink_source = isolated_source(self.root / "symlink", "cra")
        artifact = next((symlink_source / "package" / "generated").rglob("*.json"))
        artifact.unlink()
        artifact.symlink_to(symlink_source / "runtime.yaml")
        attacks.append(symlink_source)

        hardlink_source = isolated_source(self.root / "hardlink", "cra")
        artifact = next((hardlink_source / "package" / "generated").rglob("*.json"))
        os.link(artifact, hardlink_source / "package" / "duplicate.json")
        attacks.append(hardlink_source)

        writable_source = isolated_source(self.root / "writable", "cra")
        (writable_source / "runtime.yaml").chmod(0o666)
        attacks.append(writable_source)

        for source in attacks:
            with self.subTest(source=source.parent.name):
                destination = source.parent / "destination"
                destination.mkdir()
                with self.assertRaisesRegex(
                    MODULE.StagingError, MODULE.FAILURE_MESSAGE
                ):
                    MODULE.stage(
                        "cra",
                        source,
                        destination,
                        target_uid=self.uid,
                        target_gid=self.gid,
                    )

    def test_package_bounds_manifest_digest_and_authority_binding_fail_closed(
        self,
    ) -> None:
        digest_source = isolated_source(self.root / "digest", "cra")
        artifact = next((digest_source / "package" / "generated").rglob("*.json"))
        artifact.write_bytes(artifact.read_bytes() + b" ")

        oversized_source = isolated_source(self.root / "oversized", "cra")
        (oversized_source / "runtime.yaml").write_bytes(
            b"x" * (MODULE.MAX_RUNTIME_BYTES + 1)
        )

        wrong_authority_source = isolated_source(self.root / "authority", "nia")

        comment_bypass_source = isolated_source(self.root / "comment-bypass", "cra")
        (comment_bypass_source / "runtime.yaml").write_text(
            "# packagePath: /etc/relay/cra/package\n"
            "packagePath: /tmp/not-the-staged-package\n",
            encoding="utf-8",
        )

        hash_bypass_source = isolated_source(self.root / "hash-bypass", "cra")
        (hash_bypass_source / "runtime.yaml").write_text(
            "packagePath: /etc/relay/cra/package#outside-staged\n",
            encoding="utf-8",
        )

        for label, source in (
            ("digest", digest_source),
            ("oversized", oversized_source),
            ("authority", wrong_authority_source),
            ("comment-bypass", comment_bypass_source),
            ("hash-bypass", hash_bypass_source),
        ):
            with self.subTest(label=label):
                destination = source.parent / "destination"
                destination.mkdir()
                with self.assertRaisesRegex(
                    MODULE.StagingError, MODULE.FAILURE_MESSAGE
                ):
                    MODULE.stage(
                        "cra",
                        source,
                        destination,
                        target_uid=self.uid,
                        target_gid=self.gid,
                    )

    def test_read_detects_same_path_mutation_after_open(self) -> None:
        directory_fd = os.open(self.source, os.O_RDONLY | os.O_DIRECTORY)
        path = self.source / "runtime.yaml"
        metadata = path.stat()
        snapshot = MODULE._snapshot(metadata)
        real_fstat = os.fstat
        calls = 0

        def racing_fstat(descriptor: int):
            nonlocal calls
            result = real_fstat(descriptor)
            calls += 1
            if calls == 1:
                path.write_bytes(path.read_bytes() + b"\n")
            return result

        try:
            with (
                mock.patch.object(MODULE.os, "fstat", side_effect=racing_fstat),
                self.assertRaisesRegex(MODULE.StagingError, MODULE.FAILURE_MESSAGE),
            ):
                MODULE._read_exact(
                    directory_fd,
                    "runtime.yaml",
                    snapshot,
                    max_bytes=MODULE.MAX_RUNTIME_BYTES,
                )
        finally:
            os.close(directory_fd)

    def test_cli_failure_is_generic(self) -> None:
        result = MODULE.main(
            [
                "--authority",
                "unknown-sensitive-authority",
                "--source",
                str(self.source),
                "--destination",
                str(self.destination),
                "stage",
            ]
        )
        self.assertEqual(result, 1)


class LocalRelayRuntimeComposeTests(unittest.TestCase):
    def test_each_relay_has_one_isolated_stager_and_fixed_runtime_identity(
        self,
    ) -> None:
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        services = compose["services"]

        for authority in AUTHORITIES:
            stager = services[f"{authority}-relay-runtime-stager"]
            relay = services[f"{authority}-relay"]
            self.assertEqual(stager["network_mode"], "none")
            self.assertTrue(stager["read_only"])
            self.assertEqual(stager["cap_drop"], ["ALL"])
            self.assertEqual(
                set(stager["cap_add"]), {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
            )
            self.assertIn("no-new-privileges:true", stager["security_opt"])
            self.assertEqual(stager["restart"], "no")
            volumes = set(stager["volumes"])
            self.assertIn(
                f"./relays/{authority}/runtime.yaml:/source/runtime.yaml:ro",
                volumes,
            )
            self.assertIn(f"./relays/{authority}/package:/source/package:ro", volumes)
            self.assertIn(f"{authority}-relay-runtime:/staged", volumes)
            for other in set(AUTHORITIES) - {authority}:
                self.assertFalse(any(f"relays/{other}" in volume for volume in volumes))

            self.assertEqual(relay["user"], "65532:65532")
            self.assertIn(
                f"{authority}-relay-runtime:/etc/relay/{authority}:ro",
                relay["volumes"],
            )
            self.assertFalse(
                any(f"./relays/{authority}/" in volume for volume in relay["volumes"])
            )
            self.assertEqual(
                relay["depends_on"][f"{authority}-relay-runtime-stager"]["condition"],
                "service_completed_successfully",
            )

        audit_initializer = services["relay-audit-init"]
        self.assertNotIn("environment", audit_initializer)
        self.assertIn("target_uid = 65532", audit_initializer["command"][2])
        self.assertIn("target_gid = 65532", audit_initializer["command"][2])


if __name__ == "__main__":
    unittest.main()
