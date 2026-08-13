#!/usr/bin/env python3
"""Confine one hosted signing secret to one Transit proxy process."""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
import socket
import stat
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

MAX_SECRET_BYTES = 16 * 1024
SECRET_PATH = Path("/tmp/solmara-signing.jwk")
PUBLIC_PATH = Path("/tmp/solmara-signing-public.jwk")
SOCKET_PATH = Path("/transit/transit-proxy.sock")
STAGING_ROOT = Path("/tmp")
ALLOWED_KEY_NAMES = frozenset(
    {
        "solmara-mint",
        "solmara-evidence-cra",
        "solmara-evidence-nia",
        "solmara-evidence-sro",
        "solmara-evidence-mosd-programme",
        "solmara-evidence-sipf",
        "solmara-evidence-nagdi",
    }
)
GENERIC_ERROR = "hosted Transit signer could not start"


class SignerError(Exception):
    """A value-free signer configuration refusal."""


class QuietArgumentParser(argparse.ArgumentParser):
    """Keep rejected configuration values out of diagnostics."""

    def error(self, message: str) -> None:
        del message
        raise SignerError("invalid arguments")


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _file_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _directory_is_confined(metadata: os.stat_result) -> bool:
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in {0, os.geteuid()}:
        return False
    if metadata.st_mode & 0o022 == 0:
        return True
    # Root-owned sticky directories such as /tmp prevent unprivileged callers
    # from replacing a child they do not own. Every following component is
    # still opened relative to a pinned descriptor and must be owner-controlled.
    return metadata.st_uid == 0 and metadata.st_mode & stat.S_ISVTX != 0


def _open_confined_directory(path: Path) -> int:
    if not path.is_absolute():
        raise SignerError("invalid secret")
    components = path.parts[1:]
    if any(component in {"", ".", ".."} for component in components):
        raise SignerError("invalid secret")
    directory = os.open("/", _directory_flags())
    try:
        root_metadata = os.fstat(directory)
        if not _directory_is_confined(root_metadata):
            raise SignerError("invalid secret")
        for component in components:
            next_directory = os.open(component, _directory_flags(), dir_fd=directory)
            os.close(directory)
            directory = next_directory
            metadata = os.fstat(directory)
            if not _directory_is_confined(metadata):
                raise SignerError("invalid secret")
        return directory
    except OSError as error:
        os.close(directory)
        raise SignerError("invalid secret") from error
    except SignerError:
        os.close(directory)
        raise


def _open_confined_secret(path: Path) -> int:
    """Open an absolute secret without following any path component."""

    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise SignerError("invalid secret")
    directory = _open_confined_directory(path.parent)
    try:
        return os.open(path.name, _file_flags(), dir_fd=directory)
    except OSError as error:
        raise SignerError("invalid secret") from error
    finally:
        os.close(directory)


def _secret_metadata_is_confined(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid in {0, os.geteuid()}
        and metadata.st_mode & 0o022 == 0
        and metadata.st_nlink == 1
        and 0 < metadata.st_size <= MAX_SECRET_BYTES
    )


def _read_secret_descriptor(descriptor: int) -> tuple[bytearray, os.stat_result]:
    before = os.fstat(descriptor)
    if not _secret_metadata_is_confined(before):
        raise SignerError("invalid secret")

    value = bytearray()
    while len(value) <= MAX_SECRET_BYTES:
        chunk = os.read(descriptor, min(4096, MAX_SECRET_BYTES + 1 - len(value)))
        if not chunk:
            break
        value.extend(chunk)
    after = os.fstat(descriptor)
    if (
        len(value) > MAX_SECRET_BYTES
        or len(value) != before.st_size
        or (
            before.st_dev,
            before.st_ino,
            before.st_uid,
            before.st_mode,
            before.st_size,
            before.st_nlink,
        )
        != (
            after.st_dev,
            after.st_ino,
            after.st_uid,
            after.st_mode,
            after.st_size,
            after.st_nlink,
        )
    ):
        raise SignerError("invalid secret")
    return value, before


def _read_secret(path: Path) -> bytearray:
    descriptor = _open_confined_secret(path)
    try:
        value, _ = _read_secret_descriptor(descriptor)
        return value
    except OSError as error:
        raise SignerError("invalid secret") from error
    finally:
        os.close(descriptor)


def _stage_secret(
    source: Path,
    staging_root: Path = STAGING_ROOT,
    *,
    expected_digest: bytes | None = None,
) -> Path:
    value = _read_secret(source)
    try:
        if (
            expected_digest is not None
            and hashlib.sha256(value).digest() != expected_digest
        ):
            raise SignerError("invalid secret")
        directory = Path(tempfile.mkdtemp(prefix="solmara-transit-", dir=staging_root))
        directory.chmod(0o700)
        metadata = directory.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise SignerError("invalid staging area")

        destination = directory / "signing.jwk"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(destination, flags, 0o600)
        try:
            written = 0
            while written < len(value):
                written += os.write(descriptor, value[written:])
            os.fchmod(descriptor, 0o600)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size != len(value)
            ):
                raise SignerError("invalid staging area")
        finally:
            os.close(descriptor)
        return destination
    except OSError as error:
        raise SignerError("invalid staging area") from error
    finally:
        value[:] = b"\0" * len(value)


def _consume_secret(path: Path, expected_digest: bytes) -> None:
    descriptor = _open_confined_secret(path)
    value = bytearray()
    directory = -1
    try:
        value, opened = _read_secret_descriptor(descriptor)
        if hashlib.sha256(value).digest() != expected_digest:
            raise SignerError("invalid secret")
        directory = _open_confined_directory(path.parent)
        current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)

        def identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
            return (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_uid,
                metadata.st_mode,
                metadata.st_size,
                metadata.st_nlink,
            )

        if identity(current) != identity(opened):
            raise SignerError("invalid secret")
        os.unlink(path.name, dir_fd=directory)
    except OSError as error:
        raise SignerError("invalid secret") from error
    finally:
        if directory >= 0:
            os.close(directory)
        value[:] = b"\0" * len(value)
        os.close(descriptor)


def _remove_empty_staging_directory(
    path: Path, staging_root: Path = STAGING_ROOT
) -> None:
    directory = path.parent
    try:
        metadata = directory.lstat()
        if (
            directory.parent != staging_root
            or not directory.name.startswith("solmara-transit-")
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise SignerError("invalid staging area")
        directory.rmdir()
    except OSError as error:
        raise SignerError("invalid staging area") from error


def _discard_staged_secret(path: Path, expected_digest: bytes) -> None:
    _consume_secret(path, expected_digest)
    _remove_empty_staging_directory(path, path.parent.parent)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _verify_public_match(private_path: Path, public_path: Path) -> tuple[bytes, bytes]:
    private_bytes = _read_secret(private_path)
    public_bytes = _read_secret(public_path)
    try:
        private = json.loads(private_bytes.decode("utf-8"))
        public = json.loads(public_bytes.decode("utf-8"))
        private_keys = {"kty", "crv", "alg", "x", "y", "d", "kid"}
        public_keys = {"kty", "crv", "alg", "x", "y", "kid"}
        if (
            not isinstance(private, dict)
            or not isinstance(public, dict)
            or set(private) != private_keys
            or set(public) != public_keys
            or private.get("kty") != "EC"
            or private.get("crv") != "P-256"
            or private.get("alg") != "ES256"
        ):
            raise SignerError("invalid key pair")
        scalar = int.from_bytes(_b64decode(private["d"]), "big")
        numbers = (
            ec.derive_private_key(scalar, ec.SECP256R1()).public_key().public_numbers()
        )
        expected = {
            "kty": "EC",
            "crv": "P-256",
            "alg": "ES256",
            "x": _b64url(numbers.x.to_bytes(32, "big")),
            "y": _b64url(numbers.y.to_bytes(32, "big")),
        }
        thumbprint = {key: expected[key] for key in ("crv", "kty", "x", "y")}
        expected["kid"] = _b64url(
            hashlib.sha256(
                json.dumps(thumbprint, separators=(",", ":"), sort_keys=True).encode()
            ).digest()
        )
        if public != expected or any(private[key] != expected[key] for key in expected):
            raise SignerError("invalid key pair")
        return (
            hashlib.sha256(private_bytes).digest(),
            hashlib.sha256(public_bytes).digest(),
        )
    except SignerError:
        raise
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise SignerError("invalid key pair") from None
    finally:
        private_bytes[:] = b"\0" * len(private_bytes)
        public_bytes[:] = b"\0" * len(public_bytes)


def _socket_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise SignerError("invalid socket") from error
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
        or metadata.st_nlink != 1
    ):
        raise SignerError("invalid socket")
    return metadata.st_dev, metadata.st_ino, metadata.st_uid, metadata.st_mode


def _remove_stale_socket(path: Path) -> None:
    identity = _socket_identity(path)
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.25)
            client.connect(str(path))
    except (ConnectionRefusedError, FileNotFoundError):
        pass
    except OSError as error:
        if error.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
            raise SignerError("invalid socket") from error
    else:
        raise SignerError("invalid socket")

    if not path.exists() and not path.is_symlink():
        return
    if _socket_identity(path) != identity:
        raise SignerError("invalid socket")
    try:
        path.unlink()
    except OSError as error:
        raise SignerError("invalid socket") from error


def _validate_socket(path: Path) -> None:
    if path != SOCKET_PATH:
        raise SignerError("invalid socket")
    try:
        metadata = path.parent.lstat()
    except OSError as error:
        raise SignerError("invalid socket") from error
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o022
    ):
        raise SignerError("invalid socket")
    if path.exists() or path.is_symlink():
        _remove_stale_socket(path)


def _validate_proxy(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise SignerError("invalid proxy")
    try:
        metadata = path.stat()
    except OSError as error:
        raise SignerError("invalid proxy") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in {0, os.geteuid()}
        or metadata.st_mode & 0o022
    ):
        raise SignerError("invalid proxy")


def exec_signer(
    private_jwk: Path,
    public_jwk: Path,
    socket_path: Path,
    key_name: str,
    proxy: Path,
) -> None:
    if (
        private_jwk != SECRET_PATH
        or public_jwk != PUBLIC_PATH
        or key_name not in ALLOWED_KEY_NAMES
    ):
        raise SignerError("invalid signer configuration")
    private_digest, public_digest = _verify_public_match(private_jwk, public_jwk)
    _validate_socket(socket_path)
    _validate_proxy(proxy)
    staged = _stage_secret(private_jwk, expected_digest=private_digest)
    try:
        _consume_secret(private_jwk, private_digest)
        _consume_secret(public_jwk, public_digest)
    except SignerError:
        _discard_staged_secret(staged, private_digest)
        raise
    arguments = [
        sys.executable,
        str(proxy),
        "--private-jwk",
        str(staged),
        "--consume-private-jwk",
        "--socket",
        str(socket_path),
        "--key-name",
        key_name,
    ]
    environment = {
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    try:
        os.execve(sys.executable, arguments, environment)
    except OSError:
        _discard_staged_secret(staged, private_digest)
        raise


def main() -> int:
    parser = QuietArgumentParser(add_help=False)
    parser.add_argument("--private-jwk", required=True, type=Path)
    parser.add_argument("--public-jwk", required=True, type=Path)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--key-name", required=True)
    try:
        arguments = parser.parse_args()
        proxy = Path(__file__).resolve().with_name("local-transit-proxy.py")
        os.umask(0o077)
        exec_signer(
            arguments.private_jwk,
            arguments.public_jwk,
            arguments.socket,
            arguments.key_name,
            proxy,
        )
    except (OSError, SignerError, ValueError):
        print(GENERIC_ERROR, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
