#!/usr/bin/env python3
"""Archive a verified pre-v0.18 local audit chain without rewriting history."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import stat
import tempfile
from pathlib import Path


CHAIN_KEY_INFO = b"registry-platform-audit/chain-key/v1"
CHAIN_CONTEXT = b"registry-platform-audit-chain-v1"
ARCHIVE_SUFFIX = ".pre-v018-raw-hmac"
RECEIPT_SUFFIX = ".pre-v018-raw-hmac.receipt.json"
ENVELOPE_KEYS = {
    "envelope_id",
    "timestamp_unix_ms",
    "prev_hash",
    "record",
    "record_hash",
}
RECEIPT_KEYS = {
    "version",
    "archive",
    "legacyKeyMode",
    "sha256",
    "bytes",
    "records",
}


class MigrationError(RuntimeError):
    """The chain cannot be archived without weakening audit integrity."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-path", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument(
        "--legacy-key-mode", required=True, choices=("exact", "trim-newlines")
    )
    args = parser.parse_args(argv)

    try:
        result = migrate(args.audit_path, args.key_file, args.legacy_key_mode)
    except (MigrationError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"local audit migration refused: {error}\n")
    print(result)
    return 0


def migrate(audit_path: Path, key_file: Path, legacy_key_mode: str) -> str:
    validate_key_file(key_file)
    master = key_file.read_bytes()
    if len(master) < 32:
        raise MigrationError("the audit master key is shorter than 32 bytes")

    validate_parent(audit_path.parent)
    sealed = sealed_paths(audit_path)
    if sealed:
        raise MigrationError(
            "segmented legacy history requires explicit operator archival"
        )

    archive = Path(f"{audit_path}{ARCHIVE_SUFFIX}")
    receipt = Path(f"{audit_path}{RECEIPT_SUFFIX}")
    reference = audit_path if audit_path.exists() else archive
    if not reference.exists():
        if receipt.exists():
            raise MigrationError("the legacy archive receipt has no archive")
        return "local audit migration: no retained legacy records"

    validate_audit_file(reference)
    legacy_key = (
        master.rstrip(b"\r\n") if legacy_key_mode == "trim-newlines" else master
    )
    if len(legacy_key) < 32:
        raise MigrationError("the legacy audit key is shorter than 32 bytes")
    derived_key = hmac.digest(master, CHAIN_KEY_INFO + b"\x01", "sha256")

    if audit_path.exists() and audit_path.stat().st_size > 0:
        if archive.exists() and receipt.exists():
            validate_archive_receipt(
                archive,
                receipt,
                legacy_key_mode,
                legacy_key,
                create_if_missing=False,
            )
        if not archive.exists() or receipt.exists():
            try:
                contents = read_stable_contents(audit_path)
            except MigrationError:
                pass
            else:
                if verify_contents(contents, derived_key):
                    return (
                        "local audit migration: active v0.18 chain verified read-only"
                    )

    lock_path = Path(f"{audit_path}.lock")
    ensure_lock_file(lock_path, reference.stat())
    with lock_path.open("r+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return verify_active_writer(
                audit_path,
                archive,
                receipt,
                legacy_key_mode,
                master,
            )

        if archive.exists():
            validate_archive_receipt(archive, receipt, legacy_key_mode, legacy_key)

        if audit_path.exists() and audit_path.stat().st_size > 0:
            if verify(audit_path, derived_key):
                return (
                    "local audit migration: active chain already uses the v0.18 profile"
                )
            if archive.exists():
                raise MigrationError("legacy and active histories overlap")

            if not verify(audit_path, legacy_key):
                raise MigrationError(
                    "the retained chain does not verify under the expected legacy profile"
                )

            metadata = audit_path.stat()
            os.replace(audit_path, archive)
            fsync_directory(audit_path.parent)
            write_receipt(archive, receipt, legacy_key_mode, metadata)
            return (
                "local audit migration: verified legacy history archived byte-for-byte"
            )

        if audit_path.exists() and audit_path.stat().st_size == 0:
            if archive.exists():
                audit_path.unlink()
                fsync_directory(audit_path.parent)
                return (
                    "local audit migration: verified archive retained for v0.18 startup"
                )
            return "local audit migration: empty active chain needs no archive"

        if archive.exists():
            return "local audit migration: verified archive retained for v0.18 startup"
        raise MigrationError("the active chain disappeared during migration")


def verify_active_writer(
    audit_path: Path,
    archive: Path,
    receipt: Path,
    legacy_key_mode: str,
    master: bytes,
) -> str:
    """Permit a running v0.18 writer without mutating files outside the lock."""
    legacy_key = (
        master.rstrip(b"\r\n") if legacy_key_mode == "trim-newlines" else master
    )
    if archive.exists():
        validate_archive_receipt(
            archive,
            receipt,
            legacy_key_mode,
            legacy_key,
            create_if_missing=False,
        )
    if not audit_path.exists() or audit_path.stat().st_size == 0:
        raise MigrationError("an audit writer is active without a verifiable chain")

    validate_audit_file(audit_path)
    contents = read_stable_contents(audit_path)
    derived_key = hmac.digest(master, CHAIN_KEY_INFO + b"\x01", "sha256")
    if not verify_contents(contents, derived_key):
        raise MigrationError("an audit writer is active with a non-v0.18 chain")
    return "local audit migration: active v0.18 writer and chain verified read-only"


def validate_parent(path: Path) -> None:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        raise MigrationError("the audit parent is not a regular directory")
    if metadata.st_mode & 0o077:
        raise MigrationError("the audit parent is not owner-only")


def sealed_paths(audit_path: Path) -> list[Path]:
    prefix = f"{audit_path.name}."
    sealed = []
    for candidate in audit_path.parent.iterdir():
        suffix = candidate.name.removeprefix(prefix)
        if candidate.name.startswith(prefix) and len(suffix) == 8 and suffix.isdigit():
            sealed.append(candidate)
    return sorted(sealed)


def validate_key_file(path: Path) -> None:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise MigrationError("the audit key is not a singly linked regular file")
    if metadata.st_mode & 0o077:
        raise MigrationError("the audit key is not owner-only")


def validate_audit_file(path: Path) -> None:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise MigrationError("the audit history is not a singly linked regular file")
    if metadata.st_mode & 0o077:
        raise MigrationError("the audit history is not owner-only")


def ensure_lock_file(path: Path, reference: os.stat_result) -> None:
    if not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.fchown(descriptor, reference.st_uid, reference.st_gid)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fsync_directory(path.parent)
    validate_audit_file(path)


def read_envelopes(path: Path) -> list[dict[str, object]]:
    return read_envelope_contents(path.read_bytes())


def read_envelope_contents(contents: bytes) -> list[dict[str, object]]:
    envelopes: list[dict[str, object]] = []
    for raw in contents.splitlines():
        if not raw:
            raise MigrationError("the audit history contains an empty line")
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) != ENVELOPE_KEYS:
            raise MigrationError("an audit envelope has an unexpected shape")
        envelopes.append(value)
    return envelopes


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, member in pairs:
        if key in value:
            raise MigrationError("an audit JSON object contains a duplicate key")
        value[key] = member
    return value


def verify(path: Path, key: bytes) -> bool:
    try:
        return verify_contents(path.read_bytes(), key)
    except OSError:
        return False


def verify_contents(contents: bytes, key: bytes) -> bool:
    previous: str | None = None
    try:
        for envelope in read_envelope_contents(contents):
            if envelope["prev_hash"] != previous:
                return False
            expected = record_hash(envelope, key)
            if not hmac.compare_digest(expected, str(envelope["record_hash"])):
                return False
            previous = expected
    except (MigrationError, OSError, ValueError, json.JSONDecodeError):
        return False
    return True


def read_stable_contents(path: Path) -> bytes:
    for _ in range(3):
        before = path.stat(follow_symlinks=False)
        contents = path.read_bytes()
        after = path.stat(follow_symlinks=False)
        if (
            before.st_ino == after.st_ino
            and before.st_size == after.st_size == len(contents)
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return contents
    raise MigrationError("the active audit chain changed during read-only verification")


def record_hash(envelope: dict[str, object], key: bytes) -> str:
    payload = encode_json(
        {
            "envelope_id": envelope["envelope_id"],
            "timestamp_unix_ms": envelope["timestamp_unix_ms"],
            "prev_hash": envelope["prev_hash"],
            "record": envelope["record"],
        }
    )
    return hmac.new(key, CHAIN_CONTEXT + b"\x00" + payload, hashlib.sha256).hexdigest()


def write_receipt(
    archive: Path,
    receipt: Path,
    legacy_key_mode: str,
    metadata: os.stat_result,
) -> None:
    envelopes = read_envelopes(archive)
    contents = archive.read_bytes()
    document = {
        "version": 1,
        "archive": archive.name,
        "legacyKeyMode": legacy_key_mode,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
        "records": len(envelopes),
    }
    write_new_file(receipt, encode_json(document) + b"\n", metadata)


def validate_archive_receipt(
    archive: Path,
    receipt: Path,
    legacy_key_mode: str,
    legacy_key: bytes,
    *,
    create_if_missing: bool = True,
) -> None:
    validate_audit_file(archive)
    if not verify(archive, legacy_key):
        raise MigrationError("the legacy archive no longer verifies")
    if not receipt.is_file() and create_if_missing:
        write_receipt(archive, receipt, legacy_key_mode, archive.stat())
    if not receipt.is_file():
        raise MigrationError("the legacy archive receipt is missing")
    validate_audit_file(receipt)
    document = json.loads(receipt.read_bytes(), object_pairs_hook=unique_object)
    if not isinstance(document, dict) or set(document) != RECEIPT_KEYS:
        raise MigrationError("the legacy archive receipt has an unexpected shape")
    contents = archive.read_bytes()
    expected = {
        "version": 1,
        "archive": archive.name,
        "legacyKeyMode": legacy_key_mode,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
        "records": len(read_envelopes(archive)),
    }
    if document != expected:
        raise MigrationError("the legacy archive no longer matches its receipt")


def encode_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def write_new_file(path: Path, contents: bytes, metadata: os.stat_result) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, metadata.st_uid, metadata.st_gid)
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(contents)
            output.flush()
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary_path, path)
        temporary_path.unlink()
        fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
