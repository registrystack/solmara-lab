#!/usr/bin/env python3
"""Stage one authority's Relay runtime and sealed package into a local volume."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

AUTHORITIES = ("cra", "nia", "mosd", "sipf", "nagdi")
TARGET_UID = 65532
TARGET_GID = 65532
MAX_RUNTIME_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PACKAGE_FILE_BYTES = 1024 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
MAX_PACKAGE_FILES = 128
SUCCESS_MESSAGE = "Relay runtime staged"
FAILURE_MESSAGE = "Relay runtime staging failed"
LOCK_NAME = ".stager.lock"
STAGING_PACKAGE = ".staging-package"
STAGING_RUNTIME = ".staging-runtime.yaml"


class StagingError(RuntimeError):
    """A deliberately value-free staging failure."""


class QuietArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise StagingError(FAILURE_MESSAGE)


@dataclass(frozen=True)
class FileSnapshot:
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int


def _fail() -> StagingError:
    return StagingError(FAILURE_MESSAGE)


def _snapshot(metadata: os.stat_result) -> FileSnapshot:
    return FileSnapshot(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _safe_file(metadata: os.stat_result, *, max_bytes: int) -> bool:
    mode = stat.S_IMODE(metadata.st_mode)
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_nlink == 1
        and 0 <= metadata.st_size <= max_bytes
        and mode in {0o400, 0o440, 0o444, 0o600, 0o640, 0o644}
    )


def _safe_directory(metadata: os.stat_result) -> bool:
    return stat.S_ISDIR(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) in {
        0o500,
        0o550,
        0o555,
        0o700,
        0o750,
        0o755,
    }


def _open_directory(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _scan_tree(directory_fd: int) -> tuple[dict[str, FileSnapshot], set[str]]:
    files: dict[str, FileSnapshot] = {}
    directories: set[str] = set()
    total_bytes = 0

    def visit(parent_fd: int, prefix: PurePosixPath) -> None:
        nonlocal total_bytes
        with os.scandir(parent_fd) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            if entry.name in {".", ".."} or "/" in entry.name:
                raise _fail()
            metadata = entry.stat(follow_symlinks=False)
            relative = str(prefix / entry.name)
            if stat.S_ISDIR(metadata.st_mode):
                if not _safe_directory(metadata):
                    raise _fail()
                directories.add(relative)
                child_fd = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_fd,
                )
                try:
                    if _snapshot(os.fstat(child_fd)) != _snapshot(metadata):
                        raise _fail()
                    visit(child_fd, prefix / entry.name)
                finally:
                    os.close(child_fd)
                continue
            if not _safe_file(metadata, max_bytes=MAX_PACKAGE_FILE_BYTES):
                raise _fail()
            files[relative] = _snapshot(metadata)
            total_bytes += metadata.st_size
            if len(files) > MAX_PACKAGE_FILES or total_bytes > MAX_PACKAGE_BYTES:
                raise _fail()

    visit(directory_fd, PurePosixPath())
    return files, directories


def _open_relative(directory_fd: int, relative: str) -> int:
    parts = PurePosixPath(relative).parts
    if not parts:
        raise _fail()
    current_fd = os.dup(directory_fd)
    try:
        for part in parts[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        return os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=current_fd)
    finally:
        os.close(current_fd)


def _read_exact(
    directory_fd: int,
    relative: str,
    expected: FileSnapshot,
    *,
    max_bytes: int,
) -> bytes:
    descriptor = _open_relative(directory_fd, relative)
    try:
        before = os.fstat(descriptor)
        if _snapshot(before) != expected or not _safe_file(before, max_bytes=max_bytes):
            raise _fail()
        chunks: list[bytes] = []
        copied = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - copied))
            if not chunk:
                break
            copied += len(chunk)
            if copied > max_bytes:
                raise _fail()
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if _snapshot(after) != expected or copied != expected.size:
            raise _fail()
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _manifest_inventory(manifest_bytes: bytes) -> dict[str, tuple[int, str]]:
    try:
        document = json.loads(manifest_bytes)
        files = document["files"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise _fail() from None
    if not isinstance(document, dict) or not isinstance(files, list) or not files:
        raise _fail()

    inventory: dict[str, tuple[int, str]] = {}
    digest_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    for record in files:
        if not isinstance(record, dict):
            raise _fail()
        path = record.get("path")
        size = record.get("size")
        digest = record.get("sha256")
        if (
            not isinstance(path, str)
            or not path
            or len(path) > 512
            or PurePosixPath(path).is_absolute()
            or any(part in {"", ".", ".."} for part in PurePosixPath(path).parts)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_PACKAGE_FILE_BYTES
            or not isinstance(digest, str)
            or digest_pattern.fullmatch(digest) is None
            or path in inventory
            or path == "relay-package.json"
        ):
            raise _fail()
        inventory[path] = (size, digest.removeprefix("sha256:"))
    if len(inventory) + 1 > MAX_PACKAGE_FILES:
        raise _fail()
    return inventory


def _read_package(directory_fd: int) -> dict[str, bytes]:
    files, directories = _scan_tree(directory_fd)
    manifest_snapshot = files.get("relay-package.json")
    if manifest_snapshot is None or manifest_snapshot.size > MAX_MANIFEST_BYTES:
        raise _fail()
    manifest_bytes = _read_exact(
        directory_fd,
        "relay-package.json",
        manifest_snapshot,
        max_bytes=MAX_MANIFEST_BYTES,
    )
    inventory = _manifest_inventory(manifest_bytes)
    if set(files) != set(inventory) | {"relay-package.json"}:
        raise _fail()
    expected_directories = {
        str(parent)
        for path in inventory
        for parent in PurePosixPath(path).parents
        if str(parent) != "."
    }
    if directories != expected_directories:
        raise _fail()

    payloads = {"relay-package.json": manifest_bytes}
    total_bytes = len(manifest_bytes)
    for path, (expected_size, expected_digest) in sorted(inventory.items()):
        payload = _read_exact(
            directory_fd,
            path,
            files[path],
            max_bytes=MAX_PACKAGE_FILE_BYTES,
        )
        if len(payload) != expected_size:
            raise _fail()
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise _fail()
        payloads[path] = payload
        total_bytes += len(payload)
        if total_bytes > MAX_PACKAGE_BYTES:
            raise _fail()

    if _scan_tree(directory_fd) != (files, directories):
        raise _fail()
    return payloads


def _validate_runtime(runtime: bytes, authority: str) -> None:
    try:
        text = runtime.decode("utf-8")
    except UnicodeDecodeError:
        raise _fail() from None
    expected = f"/etc/relay/{authority}/package"
    exact_package_path = re.compile(
        rf"^packagePath:[ \t]+(?:{re.escape(expected)}|"
        rf'"{re.escape(expected)}"|\'{re.escape(expected)}\')'
        r"(?:[ \t]+#.*)?[ \t]*$"
    )
    entries = []
    for line in text.splitlines():
        if not line.startswith("packagePath:"):
            continue
        entries.append(line)
    if (
        "\x00" in text
        or len(entries) != 1
        or exact_package_path.fullmatch(entries[0]) is None
    ):
        raise _fail()


def _read_source(source: Path, authority: str) -> tuple[bytes, dict[str, bytes]]:
    source_fd = _open_directory(source)
    try:
        with os.scandir(source_fd) as iterator:
            entries = {
                entry.name: entry.stat(follow_symlinks=False) for entry in iterator
            }
        if set(entries) != {"runtime.yaml", "package"}:
            raise _fail()
        runtime_metadata = entries["runtime.yaml"]
        package_metadata = entries["package"]
        if not _safe_file(runtime_metadata, max_bytes=MAX_RUNTIME_BYTES):
            raise _fail()
        if not _safe_directory(package_metadata):
            raise _fail()
        runtime = _read_exact(
            source_fd,
            "runtime.yaml",
            _snapshot(runtime_metadata),
            max_bytes=MAX_RUNTIME_BYTES,
        )
        _validate_runtime(runtime, authority)
        package_fd = os.open(
            "package",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=source_fd,
        )
        try:
            if _snapshot(os.fstat(package_fd)) != _snapshot(package_metadata):
                raise _fail()
            package = _read_package(package_fd)
        finally:
            os.close(package_fd)
        with os.scandir(source_fd) as iterator:
            after = {
                entry.name: _snapshot(entry.stat(follow_symlinks=False))
                for entry in iterator
            }
        if after != {name: _snapshot(metadata) for name, metadata in entries.items()}:
            raise _fail()
        return runtime, package
    finally:
        os.close(source_fd)


def _remove_tree(parent_fd: int, name: str) -> None:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=parent_fd,
    )
    try:
        os.fchmod(descriptor, 0o700)
        with os.scandir(descriptor) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                if not _safe_directory(metadata):
                    raise _fail()
                _remove_tree(descriptor, entry.name)
            elif _safe_file(metadata, max_bytes=MAX_PACKAGE_FILE_BYTES):
                os.unlink(entry.name, dir_fd=descriptor)
            else:
                raise _fail()
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_fd)


def _validate_owned_tree(directory_fd: int, uid: int, gid: int) -> None:
    files, directories = _scan_tree(directory_fd)
    for relative in directories:
        descriptor = _open_relative(directory_fd, relative + "/.")
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if metadata.st_uid != uid or metadata.st_gid != gid:
            raise _fail()
    for relative in files:
        descriptor = _open_relative(directory_fd, relative)
        try:
            metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if metadata.st_uid != uid or metadata.st_gid != gid:
            raise _fail()


def _read_existing_package(
    parent_fd: int, name: str, uid: int, gid: int
) -> dict[str, bytes]:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=parent_fd,
    )
    try:
        _validate_owned_tree(descriptor, uid, gid)
        return _read_package(descriptor)
    finally:
        os.close(descriptor)


def _read_existing_runtime(parent_fd: int, authority: str, uid: int, gid: int) -> bytes:
    metadata = os.stat("runtime.yaml", dir_fd=parent_fd, follow_symlinks=False)
    if (
        metadata.st_uid != uid
        or metadata.st_gid != gid
        or not _safe_file(metadata, max_bytes=MAX_RUNTIME_BYTES)
    ):
        raise _fail()
    runtime = _read_exact(
        parent_fd,
        "runtime.yaml",
        _snapshot(metadata),
        max_bytes=MAX_RUNTIME_BYTES,
    )
    _validate_runtime(runtime, authority)
    return runtime


def _make_directory(parent_fd: int, name: str, uid: int, gid: int) -> int:
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        dir_fd=parent_fd,
    )
    os.fchown(descriptor, uid, gid)
    return descriptor


def _write_file(parent_fd: int, name: str, payload: bytes, uid: int, gid: int) -> None:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=parent_fd,
    )
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise _fail()
            remaining = remaining[written:]
        os.fchown(descriptor, uid, gid)
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_package(
    parent_fd: int, payloads: dict[str, bytes], uid: int, gid: int
) -> None:
    root_fd = _make_directory(parent_fd, STAGING_PACKAGE, uid, gid)
    opened: dict[PurePosixPath, int] = {PurePosixPath(): root_fd}
    try:
        directories = sorted(
            {
                parent
                for path in payloads
                for parent in PurePosixPath(path).parents
                if str(parent) != "."
            },
            key=lambda path: (len(path.parts), str(path)),
        )
        for relative in directories:
            parent = relative.parent
            opened[relative] = _make_directory(opened[parent], relative.name, uid, gid)
        for relative_string, payload in sorted(payloads.items()):
            relative = PurePosixPath(relative_string)
            _write_file(opened[relative.parent], relative.name, payload, uid, gid)
        for relative in sorted(opened, key=lambda path: len(path.parts), reverse=True):
            os.fchmod(opened[relative], 0o500)
            os.fsync(opened[relative])
    finally:
        for descriptor in set(opened.values()):
            os.close(descriptor)


def _recover_destination(
    destination_fd: int, authority: str, uid: int, gid: int
) -> None:
    with os.scandir(destination_fd) as iterator:
        entries = {entry.name: entry.stat(follow_symlinks=False) for entry in iterator}
    allowed = {
        LOCK_NAME,
        "runtime.yaml",
        "package",
        STAGING_PACKAGE,
        STAGING_RUNTIME,
    }
    if not set(entries) <= allowed:
        raise _fail()
    for name, metadata in entries.items():
        if name in {"package", STAGING_PACKAGE}:
            if not _safe_directory(metadata):
                raise _fail()
        elif not _safe_file(
            metadata,
            max_bytes=MAX_RUNTIME_BYTES if "runtime" in name else 0,
        ):
            raise _fail()

    if STAGING_PACKAGE in entries:
        _read_existing_package(destination_fd, STAGING_PACKAGE, uid, gid)
        _remove_tree(destination_fd, STAGING_PACKAGE)
    if STAGING_RUNTIME in entries:
        os.unlink(STAGING_RUNTIME, dir_fd=destination_fd)
    with os.scandir(destination_fd) as iterator:
        active = {entry.name for entry in iterator}
    has_runtime = "runtime.yaml" in active
    has_package = "package" in active
    if has_runtime != has_package:
        if has_runtime:
            os.unlink("runtime.yaml", dir_fd=destination_fd)
        if has_package:
            _read_existing_package(destination_fd, "package", uid, gid)
            _remove_tree(destination_fd, "package")
        return
    if has_runtime:
        _read_existing_runtime(destination_fd, authority, uid, gid)
        _read_existing_package(destination_fd, "package", uid, gid)


def _open_lock(destination_fd: int, uid: int, gid: int) -> int:
    descriptor = os.open(
        LOCK_NAME,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
        dir_fd=destination_fd,
    )
    metadata = os.fstat(descriptor)
    if not _safe_file(metadata, max_bytes=0):
        os.close(descriptor)
        raise _fail()
    os.fchown(descriptor, uid, gid)
    os.fchmod(descriptor, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def stage(
    authority: str,
    source: Path,
    destination: Path,
    *,
    target_uid: int = TARGET_UID,
    target_gid: int = TARGET_GID,
) -> None:
    if authority not in AUTHORITIES or target_uid <= 0 or target_gid <= 0:
        raise _fail()
    runtime, package = _read_source(source, authority)

    destination_fd = _open_directory(destination)
    lock_fd = -1
    try:
        os.fchown(destination_fd, target_uid, target_gid)
        os.fchmod(destination_fd, 0o700)
        lock_fd = _open_lock(destination_fd, target_uid, target_gid)
        _recover_destination(destination_fd, authority, target_uid, target_gid)

        with os.scandir(destination_fd) as iterator:
            active = {entry.name for entry in iterator}
        if "runtime.yaml" in active:
            existing_runtime = _read_existing_runtime(
                destination_fd, authority, target_uid, target_gid
            )
            existing_package = _read_existing_package(
                destination_fd, "package", target_uid, target_gid
            )
            if existing_runtime != runtime or existing_package != package:
                raise _fail()
            return

        _write_package(destination_fd, package, target_uid, target_gid)
        _write_file(
            destination_fd,
            STAGING_RUNTIME,
            runtime,
            target_uid,
            target_gid,
        )
        os.rename(
            STAGING_PACKAGE,
            "package",
            src_dir_fd=destination_fd,
            dst_dir_fd=destination_fd,
        )
        os.replace(
            STAGING_RUNTIME,
            "runtime.yaml",
            src_dir_fd=destination_fd,
            dst_dir_fd=destination_fd,
        )
        os.fsync(destination_fd)
        _read_existing_runtime(destination_fd, authority, target_uid, target_gid)
        _read_existing_package(destination_fd, "package", target_uid, target_gid)
    except StagingError:
        raise
    except OSError:
        raise _fail() from None
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        os.close(destination_fd)


def main(argv: list[str] | None = None) -> int:
    parser = QuietArgumentParser(add_help=False)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("command", choices=("stage",))
    try:
        arguments = parser.parse_args(argv)
        stage(
            arguments.authority,
            arguments.source,
            arguments.destination,
        )
    except (StagingError, OSError):
        print(FAILURE_MESSAGE, file=sys.stderr)
        return 1
    print(SUCCESS_MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
