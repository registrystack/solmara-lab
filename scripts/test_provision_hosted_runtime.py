from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml


SCRIPT = Path(__file__).with_name("provision-hosted-runtime.py")
SPEC = importlib.util.spec_from_file_location("provision_hosted_runtime", SCRIPT)
assert SPEC and SPEC.loader
provisioner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provisioner)


def write_manifest(root: Path) -> None:
    files = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    (root / "manifest.json").write_text(
        json.dumps({"format": 1, "files": files}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class HostedProvisionerTests(unittest.TestCase):
    def test_binary_write_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "source.sqlite"
            content = b"SQLite format 3\x00\n\xff\x00"
            provisioner._write(target, content, 0o444)
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o444)

    def test_install_resumes_exact_partial_tree_and_refuses_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged, destination = root / "staged", root / "destination"
            (staged / "nested").mkdir(parents=True)
            provisioner._write(staged / "one", b"one", 0o444)
            provisioner._write(staged / "nested" / "two", b"two", 0o444)
            destination.mkdir()
            provisioner._write(destination / "one", b"one", 0o444)

            provisioner._install_tree(staged, destination, root_mode=0o555)
            self.assertEqual((destination / "nested" / "two").read_bytes(), b"two")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)

            (destination / "one").chmod(0o644)
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._install_tree(staged, destination, root_mode=0o555)

    def test_secret_reader_rejects_writable_and_symbolic_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            safe = root / "safe"
            safe.write_bytes(b"value")
            safe.chmod(0o444)
            self.assertEqual(provisioner._read_secret(root, "safe"), b"value")

            safe.chmod(0o666)
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._read_secret(root, "safe")
            safe.chmod(0o444)
            os.symlink(safe, root / "link")
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._read_secret(root, "link")

    def test_hmac_secret_rejects_weak_or_non_text_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "hmac"
            secret.write_bytes(b"short")
            secret.chmod(0o400)
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._hmac_secret(root, "hmac")
            secret.chmod(0o600)
            secret.write_bytes(b"a" * 31 + b"\x00")
            secret.chmod(0o400)
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._hmac_secret(root, "hmac")
            secret.chmod(0o600)
            secret.write_bytes(b"a" * 32)
            secret.chmod(0o400)
            self.assertEqual(provisioner._hmac_secret(root, "hmac"), b"a" * 32)

    def test_relay_provision_preserves_database_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            relay = assets / "relays" / "cra"
            (relay / "package").mkdir(parents=True)
            (relay / "package" / "sealed.json").write_bytes(b"sealed")
            (relay / "source").mkdir()
            database = b"SQLite format 3\x00\n\xff\x00"
            (relay / "source" / "cra.sqlite").write_bytes(database)
            (relay / "runtime.yaml").write_text("version: 1\n", encoding="utf-8")
            write_manifest(assets)
            secrets = root / "unused-secrets"
            secrets.mkdir()
            runtime, source = root / "runtime", root / "source"
            arguments = provisioner.parser().parse_args(
                [
                    "provision",
                    "--target",
                    "cra-relay",
                    "--assets",
                    str(assets),
                    "--secrets",
                    str(secrets),
                    "--runtime-output",
                    str(runtime),
                    "--source-output",
                    str(source),
                ]
            )

            provisioner.provision(arguments)
            provisioner.provision(arguments)
            self.assertEqual((source / "cra.sqlite").read_bytes(), database)
            self.assertEqual(
                (runtime / "package" / "sealed.json").read_bytes(), b"sealed"
            )

    def test_relay_cli_loads_manifest_verifier_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            relay = assets / "relays" / "cra"
            (relay / "package").mkdir(parents=True)
            (relay / "package" / "sealed.json").write_bytes(b"sealed")
            (relay / "source").mkdir()
            (relay / "source" / "cra.sqlite").write_bytes(b"SQLite format 3\x00")
            (relay / "runtime.yaml").write_text("version: 1\n", encoding="utf-8")
            write_manifest(assets)
            runtime, source = root / "runtime", root / "source"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "provision",
                    "--target",
                    "cra-relay",
                    "--assets",
                    str(assets),
                    "--secrets",
                    str(root / "unused"),
                    "--runtime-output",
                    str(runtime),
                    "--source-output",
                    str(source),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), provisioner.SUCCESS)
            self.assertEqual(completed.stderr, "")

    def test_existing_direct_extract_publication_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, extracts = root / "runtime", root / "extracts"
            runtime.mkdir()
            extracts.mkdir()
            published_at = "2026-08-12T09:00:00Z"
            extract_id = "sro-poverty-20260812T090000Z"
            extract = extracts / f"{extract_id}.sqlite"
            with sqlite3.connect(extract) as connection:
                connection.execute(
                    "CREATE TABLE evidence_extract (published_at TEXT, publisher TEXT, extract_id TEXT)"
                )
                connection.execute(
                    "INSERT INTO evidence_extract VALUES (?, ?, ?)",
                    (published_at, "did:web:example", extract_id),
                )
            (runtime / "runtime.yaml").write_text(
                yaml.safe_dump(
                    {
                        "sourceExtracts": {
                            "sro-poverty-extract": {"path": f"/extracts/{extract.name}"}
                        }
                    }
                ),
                encoding="utf-8",
            )
            publisher = mock.Mock()
            with mock.patch.object(
                provisioner, "_load_publisher", return_value=publisher
            ):
                observed = provisioner._publication_time(
                    root / "assets",
                    "sro",
                    runtime,
                    extracts,
                    "2026-08-12T09:01:00Z",
                )
            self.assertEqual(observed, published_at)
            publisher.validate_extract.assert_called_once()

    def test_orphan_direct_extract_recovers_after_pre_runtime_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, extracts = root / "runtime", root / "extracts"
            runtime.mkdir()
            extracts.mkdir()
            published_at = "2026-08-12T09:00:00Z"
            extract_id = "sro-poverty-20260812T090000Z"
            extract = extracts / f"{extract_id}.sqlite"
            extract.write_bytes(b"immutable")
            extract.chmod(0o444)
            metadata = SimpleNamespace(published_at=published_at, extract_id=extract_id)
            publisher = mock.Mock()
            publisher.validate_extract.return_value = metadata
            with mock.patch.object(
                provisioner, "_load_publisher", return_value=publisher
            ):
                observed = provisioner._publication_time(
                    root / "assets",
                    "sro",
                    runtime,
                    extracts,
                    "2026-08-12T09:01:00Z",
                )
            self.assertEqual(observed, published_at)
            publisher.validate_extract.assert_called_once_with(
                extract, "sro", observed_at="2026-08-12T09:01:00Z"
            )

    def test_extract_publication_appends_and_atomically_rebinds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, extracts = root / "runtime", root / "extracts"
            runtime.mkdir()
            extracts.mkdir()
            previous_name = "sro-poverty-20260812T090000Z.sqlite"
            replacement_name = "sro-poverty-20260812T100000Z.sqlite"
            (extracts / previous_name).write_bytes(b"previous")
            (extracts / previous_name).chmod(0o444)
            extracts.chmod(0o555)
            (runtime / "runtime.yaml").write_text(
                yaml.safe_dump(
                    {
                        "listener": {"bindHost": "172.29.1.23"},
                        "sourceExtracts": {
                            "sro-poverty-extract": {
                                "path": f"/var/lib/registry-evidence/sro/extracts/{previous_name}"
                            }
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (runtime / "runtime.yaml").chmod(0o444)
            runtime.chmod(0o555)
            publisher = mock.Mock()
            publisher.timestamped_extract_id.return_value = previous_name.removesuffix(
                ".sqlite"
            )

            def stage(_assets, _cell, destination, _published_at, _observed_at):
                (destination / replacement_name).write_bytes(b"replacement")
                (destination / replacement_name).chmod(0o444)
                return replacement_name

            arguments = SimpleNamespace(
                target="sro-evidence",
                assets=root / "assets",
                runtime_output=runtime,
                extract_output=extracts,
            )
            with (
                mock.patch.object(provisioner, "verify_assets"),
                mock.patch.object(
                    provisioner,
                    "_publication_time",
                    return_value="2026-08-12T09:00:00Z",
                ),
                mock.patch.object(
                    provisioner, "_load_publisher", return_value=publisher
                ),
                mock.patch.object(provisioner, "_stage_extract", side_effect=stage),
            ):
                provisioner.publish_extract(arguments)

            self.assertEqual((extracts / previous_name).read_bytes(), b"previous")
            self.assertEqual((extracts / replacement_name).read_bytes(), b"replacement")
            config = yaml.safe_load((runtime / "runtime.yaml").read_text())
            self.assertEqual(
                Path(config["sourceExtracts"]["sro-poverty-extract"]["path"]).name,
                replacement_name,
            )
            self.assertEqual(stat.S_IMODE(runtime.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE(extracts.stat().st_mode), 0o555)

    def test_evidence_bind_address_is_closed_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arguments = provisioner.parser().parse_args(
                [
                    "provision",
                    "--target",
                    "sipf-evidence",
                    "--assets",
                    str(root / "assets"),
                    "--secrets",
                    str(root / "secrets"),
                    "--runtime-output",
                    str(root / "runtime"),
                    "--secret-output",
                    str(root / "output-secrets"),
                    "--bind-host",
                    "172.29.1.99",
                ]
            )
            with (
                mock.patch.object(provisioner, "verify_assets"),
                mock.patch.object(provisioner, "_stage_evidence") as stage,
                self.assertRaises(provisioner.ProvisionError),
            ):
                provisioner.provision(arguments)
            stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
