from __future__ import annotations

import base64
import contextlib
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
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml
from cryptography.hazmat.primitives.asymmetric import ec


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


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def key_pair() -> tuple[dict[str, str], dict[str, str]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_numbers = private_key.private_numbers()
    public_numbers = private_numbers.public_numbers
    public = {
        "alg": "ES256",
        "crv": "P-256",
        "kty": "EC",
        "x": b64url(public_numbers.x.to_bytes(32, "big")),
        "y": b64url(public_numbers.y.to_bytes(32, "big")),
    }
    thumbprint = {key: public[key] for key in ("crv", "kty", "x", "y")}
    public["kid"] = b64url(
        hashlib.sha256(
            json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()
        ).digest()
    )
    private = {**public, "d": b64url(private_numbers.private_value.to_bytes(32, "big"))}
    return public, private


def write_secret(root: Path, name: str, value: bytes | dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode() if isinstance(value, dict) else value
    path = root / name
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(data)
    path.chmod(0o400)


class HostedProvisionerTests(unittest.TestCase):
    def test_no_argument_cli_failure_is_one_generic_line(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, f"{provisioner.GENERIC_ERROR}\n")

    def test_unexpected_failures_are_redacted_at_the_command_boundary(self) -> None:
        stderr = StringIO()
        with (
            mock.patch.object(
                provisioner, "provision", side_effect=RuntimeError("canary")
            ),
            contextlib.redirect_stderr(stderr),
        ):
            result = provisioner.main(
                [
                    "provision",
                    "--target",
                    "cra-relay",
                    "--assets",
                    "/canary/assets",
                    "--secrets",
                    "/canary/secrets",
                    "--runtime-output",
                    "/canary/runtime",
                    "--source-output",
                    "/canary/source",
                ]
            )
        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), f"{provisioner.GENERIC_ERROR}\n")
        self.assertNotIn("canary", stderr.getvalue())

    def test_binary_write_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "source.sqlite"
            content = b"SQLite format 3\x00\n\xff\x00"
            provisioner._write(target, content, 0o444)
            self.assertEqual(target.read_bytes(), content)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o444)

    def test_install_is_idempotent_only_for_an_exact_existing_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged, destination = root / "staged", root / "destination"
            (staged / "nested").mkdir(parents=True)
            provisioner._write(staged / "one", b"one", 0o444)
            provisioner._write(staged / "nested" / "two", b"two", 0o444)
            destination.mkdir()
            provisioner._write(destination / "one", b"one", 0o444)

            with self.assertRaises(provisioner.ProvisionError):
                provisioner._install_tree(staged, destination, root_mode=0o555)

            provisioner._write(destination / "nested" / "two", b"two", 0o444)
            (destination / "nested").chmod(0o755)
            provisioner._install_tree(staged, destination, root_mode=0o555)
            provisioner._install_tree(staged, destination, root_mode=0o555)

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

    def test_secret_inventory_is_exact_and_authority_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_secret(root, "signing-public.jwk", b"public")
            write_secret(root, "audit-hmac-key", b"a" * 32)
            expected = {"signing-public.jwk", "audit-hmac-key"}
            provisioner._validate_secret_inventory(root, expected)

            write_secret(root, "another-authority-client-key", b"private")
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._validate_secret_inventory(root, expected)

    def test_evidence_output_contains_only_its_public_signer_and_own_secrets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            cell = assets / "evidence" / "cells" / "sipf"
            (cell / "bundle").mkdir(parents=True)
            (cell / "bundle" / "evidence.yaml").write_text(
                yaml.safe_dump({"signing": {"activePublicJwkFile": "old"}}),
                encoding="utf-8",
            )
            (cell / "runtime.yaml").write_text(
                yaml.safe_dump({"listener": {"bindHost": "old"}}),
                encoding="utf-8",
            )
            secrets = root / "inputs"
            signing_public, signing_private = key_pair()
            _, client_private = key_pair()
            write_secret(secrets, "signing-public.jwk", signing_public)
            write_secret(secrets, "audit-hmac-key", b"a" * 32)
            write_secret(secrets, "subject-binding-hmac-key", b"b" * 32)
            for client in provisioner.CELL_CLIENTS["sipf"]:
                write_secret(secrets, f"{client}-client-key", client_private)

            runtime, output_secrets = root / "runtime", root / "output-secrets"
            provisioner._stage_evidence(
                assets,
                "sipf",
                secrets,
                runtime,
                output_secrets,
                None,
                provisioner.EXPECTED_BIND_HOST["sipf"],
                "2026-08-12T00:00:00Z",
                "2026-08-12T00:00:00Z",
            )

            self.assertEqual(
                {path.name for path in output_secrets.iterdir()},
                {
                    "audit-hmac-key",
                    "subject-binding-hmac-key",
                    "sipf-pension-evidence-client-id",
                    "sipf-pension-evidence-client-key",
                    "sipf-survivor-evidence-client-id",
                    "sipf-survivor-evidence-client-key",
                },
            )
            self.assertNotIn(
                "signing", " ".join(path.name for path in output_secrets.iterdir())
            )
            public_file = (
                runtime / "bundle" / "public-keys" / f"{signing_public['kid']}.jwk.json"
            )
            self.assertEqual(json.loads(public_file.read_text()), signing_public)
            self.assertNotIn(signing_private["d"], public_file.read_text())

    def test_mint_writes_only_audit_secret_and_public_client_registrations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            (assets / "mint").mkdir(parents=True)
            (assets / "mint" / "mint.yaml").write_text(
                yaml.safe_dump(
                    {
                        "listener": {"address": "old"},
                        "signing": {"activePublicJwkFile": "old"},
                    }
                ),
                encoding="utf-8",
            )
            secrets = root / "inputs"
            public, private = key_pair()
            write_secret(secrets, "signing-public.jwk", public)
            write_secret(secrets, "audit-hmac-key", b"a" * 32)
            for client in provisioner.MINT_CLIENTS:
                write_secret(secrets, f"{client}-public.jwk", public)
            write_secret(secrets, "solmara-demo-client-public.jwk", public)

            runtime, output_secrets = root / "runtime", root / "output-secrets"
            provisioner._stage_mint(
                assets,
                secrets,
                runtime,
                output_secrets,
                provisioner.EXPECTED_BIND_HOST["mint"],
            )
            self.assertEqual(
                {path.name for path in output_secrets.iterdir()}, {"audit-hmac-key"}
            )
            emitted = "\n".join(
                path.read_text() for path in runtime.rglob("*") if path.is_file()
            )
            self.assertNotIn(private["d"], emitted)
            self.assertEqual(len(list((runtime / "clients").glob("*.yaml"))), 9)

            write_secret(secrets, "signing-public.jwk", private)
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._stage_mint(
                    assets,
                    secrets,
                    root / "bad-runtime",
                    root / "bad-secrets",
                    provisioner.EXPECTED_BIND_HOST["mint"],
                )

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
            self.assertEqual(
                stat.S_IMODE((source / "cra.sqlite").stat().st_mode), 0o444
            )

    def test_all_outputs_are_preflighted_before_any_volume_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_output = root / "runtime-output"
            runtime_output.mkdir()
            provisioner._write(runtime_output / "runtime.yaml", b"active", 0o444)
            secret_output = root / "secret-output"
            arguments = provisioner.parser().parse_args(
                [
                    "provision",
                    "--target",
                    "mint",
                    "--assets",
                    str(root / "assets"),
                    "--secrets",
                    str(root / "inputs"),
                    "--runtime-output",
                    str(runtime_output),
                    "--secret-output",
                    str(secret_output),
                    "--bind-host",
                    provisioner.EXPECTED_BIND_HOST["mint"],
                ]
            )

            def stage(_assets, _inputs, runtime, secrets, _bind):
                provisioner._write(runtime / "runtime.yaml", b"replacement", 0o444)
                provisioner._write(secrets / "audit-hmac-key", b"a" * 32, 0o400)

            with (
                mock.patch.object(provisioner, "verify_assets"),
                mock.patch.object(provisioner, "_validate_secret_inventory"),
                mock.patch.object(provisioner, "_stage_mint", side_effect=stage),
                self.assertRaises(provisioner.ProvisionError),
            ):
                provisioner.provision(arguments)
            self.assertFalse(secret_output.exists())
            self.assertEqual((runtime_output / "runtime.yaml").read_bytes(), b"active")

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

    def test_manifest_failure_precedes_every_output_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            (assets / "manifest.json").write_text("{}\n", encoding="utf-8")
            runtime, source = root / "runtime", root / "source"
            runtime.mkdir()
            source.mkdir()
            provisioner._write(runtime / "keep", b"runtime", 0o444)
            provisioner._write(source / "keep", b"source", 0o444)
            arguments = provisioner.parser().parse_args(
                [
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
                ]
            )
            with self.assertRaises(provisioner.ProvisionError):
                provisioner.provision(arguments)
            self.assertEqual((runtime / "keep").read_bytes(), b"runtime")
            self.assertEqual((source / "keep").read_bytes(), b"source")

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
                            "sro-poverty-extract": {
                                "path": f"/var/lib/registry-evidence/sro/extracts/{extract.name}"
                            }
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

    def test_stale_or_mismatched_extract_is_a_value_free_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, extracts = root / "runtime", root / "extracts"
            runtime.mkdir()
            extracts.mkdir()
            extract = extracts / "cra-birth-20260812T090000Z.sqlite"
            extract.write_bytes(b"stale-canary")
            extract.chmod(0o444)
            publisher = mock.Mock()
            publisher.validate_extract.side_effect = RuntimeError("stale-canary")
            with (
                mock.patch.object(
                    provisioner, "_load_publisher", return_value=publisher
                ),
                self.assertRaisesRegex(provisioner.ProvisionError, "invalid existing"),
            ):
                provisioner._publication_time(
                    root / "assets",
                    "cra",
                    runtime,
                    extracts,
                    "2026-08-13T09:01:00Z",
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
            rollback = (
                runtime
                / f"runtime.rollback-{previous_name.removesuffix('.sqlite')}.yaml"
            )
            self.assertTrue(rollback.is_file())
            rollback_config = yaml.safe_load(rollback.read_text())
            self.assertEqual(
                Path(
                    rollback_config["sourceExtracts"]["sro-poverty-extract"]["path"]
                ).name,
                previous_name,
            )

    def test_extract_append_never_overwrites_a_mismatched_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged.sqlite"
            destination = root / "extracts"
            destination.mkdir()
            target = destination / staged.name
            staged.write_bytes(b"replacement")
            target.write_bytes(b"active")
            with self.assertRaises(provisioner.ProvisionError):
                provisioner._append_file(staged, destination)
            self.assertEqual(target.read_bytes(), b"active")

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

    def test_init_audit_changes_only_each_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "audit"
            root.mkdir()
            child = root / "existing.jsonl"
            child.write_bytes(b"existing-audit-canary")
            child.chmod(0o640)
            with (
                mock.patch.object(provisioner.os, "chown") as chown,
                mock.patch.object(provisioner.os, "chmod") as chmod,
            ):
                provisioner.init_audit([root], 65532, 65532)
            chown.assert_called_once_with(root, 65532, 65532)
            chmod.assert_called_once_with(root, 0o700)
            self.assertEqual(child.read_bytes(), b"existing-audit-canary")
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o640)


if __name__ == "__main__":
    unittest.main()
