#!/usr/bin/env python3
"""Publish authority-isolated Relay SQLite sources into local named volumes.

The command deliberately reports only a generic operation result. Source rows,
selectors, backup contents, and database diagnostics never cross its output
boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTHORITIES = ("cra", "nia", "mosd", "sipf", "nagdi")
EXPECTED_OBJECTS = {
    "cra": {
        ("table", "civil_person_source"),
        ("view", "relay_civil_person"),
    },
    "nia": {
        ("table", "population_person_source"),
        ("view", "relay_population_person"),
    },
    "mosd": {
        ("table", "beneficiary_enrolment_source"),
        ("view", "relay_beneficiary_enrolment"),
    },
    "sipf": {
        ("table", "pension_case_source"),
        ("table", "survivor_case_source"),
        ("view", "relay_pension_payment"),
        ("view", "relay_survivor_case"),
    },
    "nagdi": {
        ("table", "farmer_voucher_source"),
        ("table", "livestock_movement_source"),
        ("view", "relay_farmer_voucher"),
        ("view", "relay_livestock_movement"),
    },
}
MOSD_CONTROL_SELECTOR = "2300010248"
MOSD_TABLE = "beneficiary_enrolment_source"
MOSD_COLUMNS = (
    "record_id",
    "record_revision",
    "lifecycle_state",
    "recorded_at",
    "uin",
    "duplicate_flag",
)
BACKUP_NAME = ".lifecycle-proof-backup.json"
BACKUP_VERSION = 1
SUCCESS_MESSAGE = "publisher operation completed"
FAILURE_MESSAGE = "publisher operation failed"


class PublisherError(RuntimeError):
    """A deliberately value-free publisher failure."""


class QuietArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise PublisherError(FAILURE_MESSAGE)


def _fail() -> PublisherError:
    return PublisherError(FAILURE_MESSAGE)


def _expected_filename(authority: str) -> str:
    return f"{authority}.sqlite"


def _validate_paths(authority: str, database: Path, seed: Path) -> None:
    if authority not in EXPECTED_OBJECTS:
        raise _fail()
    expected = _expected_filename(authority)
    if database.name != expected or seed.name != expected:
        raise _fail()
    if database.resolve(strict=False) == seed.resolve(strict=False):
        raise _fail()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except (OSError, sqlite3.Error):
        raise _fail() from None


def _structural_schema(path: Path, authority: str) -> tuple[Any, ...]:
    try:
        if not path.is_file() or path.is_symlink():
            raise _fail()
        with _connect_read_only(path) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchall()
            if integrity != [("ok",)]:
                raise _fail()
            objects = connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
            object_names = {(row[0], row[1]) for row in objects}
            if object_names != EXPECTED_OBJECTS[authority]:
                raise _fail()
            user_version = connection.execute("PRAGMA user_version").fetchone()
            application_id = connection.execute("PRAGMA application_id").fetchone()
            encoding = connection.execute("PRAGMA encoding").fetchone()
            return (tuple(objects), user_version, application_id, encoding)
    except PublisherError:
        raise
    except (OSError, sqlite3.Error):
        raise _fail() from None


def _validate_schema_match(authority: str, database: Path, seed: Path) -> None:
    seed_schema = _structural_schema(seed, authority)
    database_schema = _structural_schema(database, authority)
    if database_schema != seed_schema:
        raise _fail()


def _validate_database(authority: str, database: Path, seed: Path) -> None:
    _validate_paths(authority, database, seed)
    _validate_schema_match(authority, database, seed)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_seeded(authority: str, database: Path, seed: Path) -> None:
    database = database.absolute()
    seed = seed.absolute()
    _validate_paths(authority, database, seed)
    _structural_schema(seed, authority)
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(database):
            _validate_database(authority, database, seed)
            return

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{database.name}.", suffix=".tmp", dir=database.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as output, seed.open("rb") as source:
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
        # The publisher remains the sole writer. Relay mounts the authority
        # volume read-only and may run under a different unprivileged UID.
        temporary.chmod(
            stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IRGRP
            | stat.S_IROTH
        )
        _validate_schema_match(authority, temporary, seed)
        try:
            os.link(temporary, database)
        except FileExistsError:
            _validate_database(authority, database, seed)
        _fsync_directory(database.parent)
        _validate_database(authority, database, seed)
    except PublisherError:
        raise
    except (OSError, sqlite3.Error):
        raise _fail() from None
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)


def _backup_path(database: Path) -> Path:
    return database.parent / BACKUP_NAME


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _backup_envelope(database: Path, row: tuple[Any, ...]) -> dict[str, Any]:
    identity = database.stat()
    payload: dict[str, Any] = {
        "version": BACKUP_VERSION,
        "authority": "mosd",
        "database_device": identity.st_dev,
        "database_inode": identity.st_ino,
        "row": list(row),
    }
    return {
        "payload": payload,
        "sha256": hashlib.sha256(_json_bytes(payload)).hexdigest(),
    }


def _read_backup(database: Path) -> dict[str, Any]:
    path = _backup_path(database)
    try:
        if not path.is_file() or path.is_symlink():
            raise _fail()
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise _fail()
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"}:
            raise _fail()
        payload = envelope["payload"]
        if not isinstance(payload, dict) or set(payload) != {
            "version",
            "authority",
            "database_device",
            "database_inode",
            "row",
        }:
            raise _fail()
        if hashlib.sha256(_json_bytes(payload)).hexdigest() != envelope["sha256"]:
            raise _fail()
        identity = database.stat()
        if (
            payload["version"] != BACKUP_VERSION
            or payload["authority"] != "mosd"
            or payload["database_device"] != identity.st_dev
            or payload["database_inode"] != identity.st_ino
            or not isinstance(payload["row"], list)
            or len(payload["row"]) != len(MOSD_COLUMNS)
            or payload["row"][4] != MOSD_CONTROL_SELECTOR
        ):
            raise _fail()
        return payload
    except PublisherError:
        raise
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise _fail() from None


def _write_backup(database: Path, envelope: dict[str, Any]) -> None:
    path = _backup_path(database)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{BACKUP_NAME}.", suffix=".tmp", dir=database.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(_json_bytes(envelope))
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _read_backup(database)
        _fsync_directory(database.parent)
    except PublisherError:
        raise
    except OSError:
        raise _fail() from None
    finally:
        temporary.unlink(missing_ok=True)


def _validate_mosd(authority: str, database: Path, seed: Path) -> None:
    if authority != "mosd":
        raise _fail()
    _validate_database(authority, database, seed)


def _open_mutable(database: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(database)
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        return connection
    except sqlite3.Error:
        raise _fail() from None


def _control_row(connection: sqlite3.Connection) -> tuple[Any, ...]:
    try:
        row = connection.execute(
            f"SELECT {', '.join(MOSD_COLUMNS)} FROM {MOSD_TABLE} WHERE uin = ?",
            (MOSD_CONTROL_SELECTOR,),
        ).fetchone()
        if row is None:
            raise _fail()
        return tuple(row)
    except PublisherError:
        raise
    except sqlite3.Error:
        raise _fail() from None


def begin_proof(authority: str, database: Path, seed: Path) -> None:
    database = database.absolute()
    seed = seed.absolute()
    _validate_mosd(authority, database, seed)
    backup = _backup_path(database)
    if os.path.lexists(backup):
        _read_backup(database)
        return
    try:
        with _open_mutable(database) as connection:
            row = _control_row(connection)
        _write_backup(database, _backup_envelope(database, row))
    except PublisherError:
        raise
    except (OSError, sqlite3.Error):
        raise _fail() from None


def _revision(row: tuple[Any, ...], recorded_at: str) -> str:
    value = {
        "record_id": str(row[0]),
        "lifecycle_state": str(row[2]),
        "recorded_at": recorded_at,
        "uin": MOSD_CONTROL_SELECTOR,
        "duplicate_flag": 1,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"rev-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _assert_same_inode(database: Path, before: os.stat_result) -> None:
    after = database.stat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise _fail()


def set_proof_state(authority: str, database: Path, seed: Path) -> None:
    database = database.absolute()
    seed = seed.absolute()
    _validate_mosd(authority, database, seed)
    payload = _read_backup(database)
    before = database.stat()
    try:
        with _open_mutable(database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = _control_row(connection)
            if row[0] != payload["row"][0] or row[4] != payload["row"][4]:
                raise _fail()
            if row[5] != 1:
                recorded_at = (
                    datetime.now(UTC)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
                cursor = connection.execute(
                    f"""
                    UPDATE {MOSD_TABLE}
                    SET duplicate_flag = ?, record_revision = ?, recorded_at = ?
                    WHERE uin = ?
                    """,
                    (1, _revision(row, recorded_at), recorded_at, MOSD_CONTROL_SELECTOR),
                )
                if cursor.rowcount != 1:
                    raise _fail()
            connection.commit()
        _assert_same_inode(database, before)
    except PublisherError:
        raise
    except (OSError, sqlite3.Error):
        raise _fail() from None


def restore_proof(authority: str, database: Path, seed: Path) -> None:
    database = database.absolute()
    seed = seed.absolute()
    _validate_mosd(authority, database, seed)
    backup = _backup_path(database)
    if not os.path.lexists(backup):
        return
    payload = _read_backup(database)
    before = database.stat()
    row = payload["row"]
    try:
        with _open_mutable(database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _control_row(connection)
            if current[0] != row[0] or current[4] != row[4]:
                raise _fail()
            assignments = ", ".join(f"{column} = ?" for column in MOSD_COLUMNS)
            cursor = connection.execute(
                f"UPDATE {MOSD_TABLE} SET {assignments} WHERE uin = ?",
                (*row, MOSD_CONTROL_SELECTOR),
            )
            if cursor.rowcount != 1:
                raise _fail()
            connection.commit()
        _assert_same_inode(database, before)
        backup.unlink()
        _fsync_directory(database.parent)
    except PublisherError:
        raise
    except (OSError, sqlite3.Error):
        raise _fail() from None


def _parser() -> argparse.ArgumentParser:
    parser = QuietArgumentParser(description="Manage a local Relay source")
    parser.add_argument("--authority", choices=AUTHORITIES, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("ensure-seeded", "begin-proof", "set-proof-state", "restore-proof"):
        commands.add_parser(command)
    return parser


def run(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    operations = {
        "ensure-seeded": ensure_seeded,
        "begin-proof": begin_proof,
        "set-proof-state": set_proof_state,
        "restore-proof": restore_proof,
    }
    operations[args.command](args.authority, args.database, args.seed)


def main() -> None:
    try:
        run()
    except (PublisherError, OSError, sqlite3.Error):
        print(FAILURE_MESSAGE, file=sys.stderr)
        raise SystemExit(1) from None
    print(SUCCESS_MESSAGE)


if __name__ == "__main__":
    main()
