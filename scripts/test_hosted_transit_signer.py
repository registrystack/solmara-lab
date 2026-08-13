from __future__ import annotations

import importlib.util
import base64
import hashlib
import json
import os
import socket
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric import ec

SCRIPT = Path(__file__).with_name("hosted-transit-signer.py")
SPEC = importlib.util.spec_from_file_location("hosted_transit_signer", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HostedTransitSignerTests(unittest.TestCase):
    def setUp(self) -> None:
        safe_parent = Path(__file__).resolve().parent
        self.temporary = tempfile.TemporaryDirectory(dir=safe_parent)
        self.root = Path(self.temporary.name)
        self.socket_temporary = tempfile.TemporaryDirectory(dir="/tmp", prefix="hst-")
        self.socket_root = Path(self.socket_temporary.name)
        self.secret_directory = self.root / "secrets"
        self.secret_directory.mkdir(mode=0o700)
        self.secret = self.secret_directory / "signing.jwk"
        self.canary = b'{"d":"PRIVATE-SIGNER-CANARY"}'
        self.secret.write_bytes(self.canary)
        self.secret.chmod(0o400)
        self.public = self.secret_directory / "signing-public.jwk"
        self.public.write_bytes(b"{}")
        self.public.chmod(0o400)
        self.staging = self.root / "staging"
        self.staging.mkdir(mode=0o700)

    def tearDown(self) -> None:
        self.socket_temporary.cleanup()
        self.temporary.cleanup()

    def test_compose_secret_is_copied_to_owner_only_staging(self) -> None:
        staged = MODULE._stage_secret(self.secret, self.staging)

        self.assertEqual(staged.read_bytes(), self.canary)
        self.assertEqual(stat.S_IMODE(staged.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(staged.parent.stat().st_mode), 0o700)
        self.assertEqual(staged.stat().st_uid, os.geteuid())

    def test_consumed_secret_is_unlinked_only_when_its_digest_still_matches(
        self,
    ) -> None:
        digest = hashlib.sha256(self.canary).digest()
        MODULE._consume_secret(self.secret, digest)
        self.assertFalse(self.secret.exists())

        replacement = self.secret_directory / "replacement.jwk"
        replacement.write_bytes(self.canary)
        replacement.chmod(0o400)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._consume_secret(replacement, hashlib.sha256(b"other").digest())
        self.assertTrue(replacement.exists())

    def test_only_root_owned_sticky_writable_parent_is_confined(self) -> None:
        def directory(mode: int, uid: int = 0) -> os.stat_result:
            return os.stat_result([stat.S_IFDIR | mode, 1, 0, 1, uid, 0, 0, 0, 0, 0])

        self.assertTrue(MODULE._directory_is_confined(directory(0o755)))
        self.assertTrue(MODULE._directory_is_confined(directory(0o1777)))
        self.assertFalse(MODULE._directory_is_confined(directory(0o0777)))
        self.assertFalse(
            MODULE._directory_is_confined(directory(0o1777, os.geteuid() + 1))
        )

    def test_private_key_must_match_exact_public_projection(self) -> None:
        private = ec.generate_private_key(ec.SECP256R1()).private_numbers()
        numbers = private.public_numbers

        def encode(value: int) -> str:
            return (
                base64.urlsafe_b64encode(value.to_bytes(32, "big"))
                .rstrip(b"=")
                .decode()
            )

        public = {
            "kty": "EC",
            "crv": "P-256",
            "alg": "ES256",
            "x": encode(numbers.x),
            "y": encode(numbers.y),
        }
        thumbprint = {key: public[key] for key in ("crv", "kty", "x", "y")}
        public["kid"] = (
            base64.urlsafe_b64encode(
                hashlib.sha256(
                    json.dumps(
                        thumbprint, separators=(",", ":"), sort_keys=True
                    ).encode()
                ).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        private_jwk = {
            **public,
            "d": encode(private.private_value),
        }
        self.secret.chmod(0o600)
        self.secret.write_text(json.dumps(private_jwk), encoding="utf-8")
        self.secret.chmod(0o400)
        self.public.chmod(0o600)
        self.public.write_text(json.dumps(public), encoding="utf-8")
        self.public.chmod(0o400)
        MODULE._verify_public_match(self.secret, self.public)

        public["x"] = encode(numbers.x - 1)
        self.public.chmod(0o600)
        self.public.write_text(json.dumps(public), encoding="utf-8")
        self.public.chmod(0o400)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid key pair"):
            MODULE._verify_public_match(self.secret, self.public)

    def test_symlinked_secret_or_parent_is_refused(self) -> None:
        link = self.secret_directory / "linked.jwk"
        link.symlink_to(self.secret)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(link)

        linked_parent = self.root / "linked-parent"
        linked_parent.symlink_to(self.secret_directory, target_is_directory=True)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(linked_parent / self.secret.name)

    def test_writable_hardlinked_empty_and_oversized_secrets_are_refused(self) -> None:
        self.secret.chmod(0o620)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(self.secret)

        self.secret.chmod(0o400)
        hardlink = self.secret_directory / "hardlink.jwk"
        os.link(self.secret, hardlink)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(self.secret)
        hardlink.unlink()

        self.secret.chmod(0o600)
        self.secret.write_bytes(b"")
        self.secret.chmod(0o400)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(self.secret)
        self.secret.chmod(0o600)
        self.secret.write_bytes(b"x" * (MODULE.MAX_SECRET_BYTES + 1))
        self.secret.chmod(0o400)
        with self.assertRaisesRegex(MODULE.SignerError, "invalid secret"):
            MODULE._read_secret(self.secret)

    def test_socket_requires_the_exact_absent_path_and_private_owned_directory(
        self,
    ) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        exact_socket = socket_directory / "transit-proxy.sock"
        with mock.patch.object(MODULE, "SOCKET_PATH", exact_socket):
            MODULE._validate_socket(exact_socket)

            exact_socket.write_text("replacement", encoding="ascii")
            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(exact_socket)
            exact_socket.unlink()

            socket_directory.chmod(0o770)
            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(exact_socket)

            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(socket_directory / "other.sock")

    def test_stale_owned_socket_is_removed_but_live_socket_is_refused(self) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        exact_socket = socket_directory / "transit-proxy.sock"
        with mock.patch.object(MODULE, "SOCKET_PATH", exact_socket):
            stale = socket.socket(socket.AF_UNIX)
            stale.bind(str(exact_socket))
            stale.close()
            exact_socket.chmod(0o600)
            MODULE._validate_socket(exact_socket)
            self.assertFalse(exact_socket.exists())

            live = socket.socket(socket.AF_UNIX)
            live.bind(str(exact_socket))
            live.listen(1)
            exact_socket.chmod(0o600)
            try:
                with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                    MODULE._validate_socket(exact_socket)
                self.assertTrue(exact_socket.exists())
            finally:
                live.close()
                exact_socket.unlink(missing_ok=True)

    def test_stale_socket_refuses_symlink_regular_file_and_open_mode(self) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        exact_socket = socket_directory / "transit-proxy.sock"
        with mock.patch.object(MODULE, "SOCKET_PATH", exact_socket):
            regular = self.root / "regular"
            regular.write_text("replacement", encoding="ascii")
            exact_socket.symlink_to(regular)
            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(exact_socket)
            exact_socket.unlink()

            exact_socket.write_text("replacement", encoding="ascii")
            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(exact_socket)
            exact_socket.unlink()

            stale = socket.socket(socket.AF_UNIX)
            stale.bind(str(exact_socket))
            stale.close()
            exact_socket.chmod(0o660)
            with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
                MODULE._validate_socket(exact_socket)
            exact_socket.unlink()

    def test_stale_socket_owned_by_another_uid_is_refused(self) -> None:
        class ForeignSocket:
            def lstat(self) -> os.stat_result:
                values = [
                    stat.S_IFSOCK | 0o600,
                    1,
                    MODULE.os.geteuid() + 1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ]
                return os.stat_result(values)

        with self.assertRaisesRegex(MODULE.SignerError, "invalid socket"):
            MODULE._socket_identity(ForeignSocket())

    def test_stale_socket_inode_replacement_is_refused_without_unlinking_replacement(
        self,
    ) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        exact_socket = socket_directory / "transit-proxy.sock"
        first = socket.socket(socket.AF_UNIX)
        first.bind(str(exact_socket))
        first.close()
        exact_socket.chmod(0o600)

        replacement = socket.socket(socket.AF_UNIX)
        replacement_path = socket_directory / "replacement.sock"
        replacement.bind(str(replacement_path))
        replacement_path.chmod(0o600)

        original = MODULE._socket_identity

        def replace_before_recheck(path: Path) -> tuple[int, int, int, int]:
            identity = original(path)
            if replace_before_recheck.calls == 0:
                replace_before_recheck.calls += 1
                return identity
            os.replace(replacement_path, path)
            return original(path)

        replace_before_recheck.calls = 0
        with (
            mock.patch.object(MODULE, "SOCKET_PATH", exact_socket),
            mock.patch.object(
                MODULE, "_socket_identity", side_effect=replace_before_recheck
            ),
            self.assertRaisesRegex(MODULE.SignerError, "invalid socket"),
        ):
            MODULE._validate_socket(exact_socket)
        self.assertTrue(exact_socket.exists())
        replacement.close()
        exact_socket.unlink(missing_ok=True)

    def test_exec_is_one_proxy_one_staged_key_and_one_exact_socket(self) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        socket_path = socket_directory / "transit-proxy.sock"
        proxy = self.root / "local-transit-proxy.py"
        proxy.write_text("# fixed proxy\n", encoding="ascii")
        proxy.chmod(0o500)
        key_name = "solmara-evidence-cra"
        stage_secret = MODULE._stage_secret
        private_digest = hashlib.sha256(self.canary).digest()
        public_digest = hashlib.sha256(b"{}").digest()

        with (
            mock.patch.object(MODULE, "SECRET_PATH", self.secret),
            mock.patch.object(MODULE, "PUBLIC_PATH", self.public),
            mock.patch.object(MODULE, "SOCKET_PATH", socket_path),
            mock.patch.object(MODULE, "STAGING_ROOT", self.staging),
            mock.patch.object(
                MODULE,
                "_stage_secret",
                side_effect=lambda source, **kwargs: stage_secret(
                    source, self.staging, **kwargs
                ),
            ),
            mock.patch.object(
                MODULE,
                "_verify_public_match",
                return_value=(private_digest, public_digest),
            ),
            mock.patch.object(
                MODULE.os, "execve", side_effect=RuntimeError("exec captured")
            ) as execute,
            self.assertRaisesRegex(RuntimeError, "exec captured"),
        ):
            MODULE.exec_signer(self.secret, self.public, socket_path, key_name, proxy)

        executable, arguments, environment = execute.call_args.args
        self.assertEqual(executable, os.sys.executable)
        self.assertEqual(arguments[0:2], [os.sys.executable, str(proxy)])
        self.assertEqual(
            arguments[-4:], ["--socket", str(socket_path), "--key-name", key_name]
        )
        staged = Path(arguments[3])
        self.assertNotEqual(staged, self.secret)
        self.assertEqual(staged.read_bytes(), self.canary)
        self.assertIn("--consume-private-jwk", arguments)
        self.assertFalse(self.secret.exists())
        self.assertFalse(self.public.exists())
        self.assertNotIn(self.canary.decode("ascii"), repr(execute.call_args))
        self.assertEqual(
            set(environment), {"LANG", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}
        )

    def test_failed_exec_removes_the_private_staging_file_and_directory(self) -> None:
        socket_directory = self.socket_root / "transit"
        socket_directory.mkdir(mode=0o700)
        socket_path = socket_directory / "transit-proxy.sock"
        proxy = self.root / "local-transit-proxy.py"
        proxy.write_text("# fixed proxy\n", encoding="ascii")
        proxy.chmod(0o500)
        private_digest = hashlib.sha256(self.canary).digest()
        public_digest = hashlib.sha256(b"{}").digest()
        stage_secret = MODULE._stage_secret

        with (
            mock.patch.object(MODULE, "SECRET_PATH", self.secret),
            mock.patch.object(MODULE, "PUBLIC_PATH", self.public),
            mock.patch.object(MODULE, "SOCKET_PATH", socket_path),
            mock.patch.object(MODULE, "STAGING_ROOT", self.staging),
            mock.patch.object(
                MODULE,
                "_stage_secret",
                side_effect=lambda source, **kwargs: stage_secret(
                    source, self.staging, **kwargs
                ),
            ),
            mock.patch.object(
                MODULE,
                "_verify_public_match",
                return_value=(private_digest, public_digest),
            ),
            mock.patch.object(MODULE.os, "execve", side_effect=OSError("refused")),
            self.assertRaises(OSError),
        ):
            MODULE.exec_signer(
                self.secret,
                self.public,
                socket_path,
                "solmara-evidence-cra",
                proxy,
            )

        self.assertEqual(list(self.staging.iterdir()), [])
        self.assertFalse(self.secret.exists())
        self.assertFalse(self.public.exists())

    def test_unlisted_key_and_noncanonical_secret_fail_before_staging(self) -> None:
        with mock.patch.object(MODULE, "_stage_secret") as stage:
            with self.assertRaisesRegex(
                MODULE.SignerError, "invalid signer configuration"
            ):
                MODULE.exec_signer(
                    Path("/another/secret"),
                    MODULE.PUBLIC_PATH,
                    MODULE.SOCKET_PATH,
                    "private-canary",
                    Path("/proxy"),
                )
        stage.assert_not_called()

    def test_cli_failure_is_generic_and_redacts_rejected_values(self) -> None:
        error = StringIO()
        canaries = ["PRIVATE-PATH-CANARY", "PRIVATE-KEY-CANARY"]
        with (
            mock.patch.object(
                os.sys,
                "argv",
                [
                    SCRIPT.name,
                    "--private-jwk",
                    canaries[0],
                    "--socket",
                    "/wrong",
                    "--key-name",
                    canaries[1],
                ],
            ),
            redirect_stderr(error),
        ):
            self.assertEqual(MODULE.main(), 1)

        self.assertEqual(error.getvalue().strip(), MODULE.GENERIC_ERROR)
        for canary in canaries:
            self.assertNotIn(canary, error.getvalue())


if __name__ == "__main__":
    unittest.main()
