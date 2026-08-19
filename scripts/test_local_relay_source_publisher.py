from __future__ import annotations

import importlib.util
import json
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("local-relay-source-publisher.py")
SPEC = importlib.util.spec_from_file_location("local_relay_source_publisher", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

CONTROL_ROW = (
    "MOSD-ENROL-CONTROL",
    "rev-original",
    "active",
    "2026-07-04T09:00:00Z",
    MODULE.MOSD_CONTROL_SELECTOR,
    0,
)


def create_mosd_database(path: Path, *, include_control: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode = DELETE;
            PRAGMA user_version = 1;
            CREATE TABLE beneficiary_enrolment_source (
                record_id TEXT PRIMARY KEY,
                record_revision TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                uin TEXT NOT NULL UNIQUE,
                duplicate_flag INTEGER NOT NULL CHECK (duplicate_flag IN (0, 1))
            ) STRICT;
            CREATE VIEW relay_beneficiary_enrolment AS
            SELECT record_id, record_revision, lifecycle_state, recorded_at,
                   uin, duplicate_flag
            FROM beneficiary_enrolment_source;
            """
        )
        if include_control:
            connection.execute(
                "INSERT INTO beneficiary_enrolment_source VALUES (?, ?, ?, ?, ?, ?)",
                CONTROL_ROW,
            )


def create_cra_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA journal_mode = DELETE;
            PRAGMA user_version = 1;
            CREATE TABLE civil_person_source (
                record_id TEXT PRIMARY KEY,
                record_revision TEXT NOT NULL,
                lifecycle_state TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                uin TEXT NOT NULL UNIQUE,
                deceased INTEGER NOT NULL CHECK (deceased IN (0, 1))
            ) STRICT;
            CREATE VIEW relay_civil_person AS
            SELECT record_id, record_revision, lifecycle_state, recorded_at,
                   uin, deceased
            FROM civil_person_source;
            """
        )


def read_control(path: Path) -> tuple[object, ...]:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT record_id, record_revision, lifecycle_state, recorded_at,
                   uin, duplicate_flag
            FROM beneficiary_enrolment_source
            WHERE uin = ?
            """,
            (MODULE.MOSD_CONTROL_SELECTOR,),
        ).fetchone()
    assert row is not None
    return row


class LocalRelaySourcePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed" / "mosd.sqlite"
        self.database = self.root / "volume" / "mosd.sqlite"
        create_mosd_database(self.seed)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_seed_is_published_once_and_existing_content_is_preserved(self) -> None:
        MODULE.ensure_seeded("mosd", self.database, self.seed)
        original_inode = self.database.stat().st_ino
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o644)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE beneficiary_enrolment_source
                SET duplicate_flag = 1, record_revision = 'rev-runtime'
                WHERE uin = ?
                """,
                (MODULE.MOSD_CONTROL_SELECTOR,),
            )

        MODULE.ensure_seeded("mosd", self.database, self.seed)

        self.assertEqual(self.database.stat().st_ino, original_inode)
        self.assertEqual(read_control(self.database)[1::4], ("rev-runtime", 1))

    def test_authority_filename_and_schema_isolation_are_enforced(self) -> None:
        cra_seed = self.root / "cra-seed" / "cra.sqlite"
        cra_database = self.root / "cra-volume" / "cra.sqlite"
        create_cra_database(cra_seed)
        MODULE.ensure_seeded("cra", cra_database, cra_seed)

        with self.assertRaisesRegex(MODULE.PublisherError, MODULE.FAILURE_MESSAGE):
            MODULE.ensure_seeded("mosd", cra_database, cra_seed)

        wrong_schema = self.root / "other-volume" / "mosd.sqlite"
        wrong_schema.parent.mkdir(parents=True)
        wrong_schema.write_bytes(cra_seed.read_bytes())
        with self.assertRaisesRegex(MODULE.PublisherError, MODULE.FAILURE_MESSAGE):
            MODULE.ensure_seeded("mosd", wrong_schema, self.seed)

    def test_existing_database_must_match_the_seed_structure_exactly(self) -> None:
        MODULE.ensure_seeded("mosd", self.database, self.seed)
        inode = self.database.stat().st_ino
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP VIEW relay_beneficiary_enrolment")
            connection.execute(
                """
                CREATE VIEW relay_beneficiary_enrolment AS
                SELECT record_id, uin FROM beneficiary_enrolment_source
                """
            )

        with self.assertRaisesRegex(MODULE.PublisherError, MODULE.FAILURE_MESSAGE):
            MODULE.ensure_seeded("mosd", self.database, self.seed)
        self.assertEqual(self.database.stat().st_ino, inode)

    def test_proof_mutates_and_restores_the_exact_row_on_the_same_inode(self) -> None:
        MODULE.ensure_seeded("mosd", self.database, self.seed)
        before = read_control(self.database)
        inode = self.database.stat().st_ino

        MODULE.begin_proof("mosd", self.database, self.seed)
        backup = self.database.parent / MODULE.BACKUP_NAME
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)

        MODULE.set_proof_state("mosd", self.database, self.seed)
        changed = read_control(self.database)
        self.assertEqual(changed[5], 1)
        self.assertNotEqual(changed[1], before[1])
        self.assertNotEqual(changed[3], before[3])
        self.assertEqual(self.database.stat().st_ino, inode)

        MODULE.restore_proof("mosd", self.database, self.seed)
        self.assertEqual(read_control(self.database), before)
        self.assertEqual(self.database.stat().st_ino, inode)
        self.assertFalse(backup.exists())

        MODULE.restore_proof("mosd", self.database, self.seed)
        self.assertEqual(read_control(self.database), before)

    def test_existing_backup_supports_crash_recovery_without_recapture(self) -> None:
        MODULE.ensure_seeded("mosd", self.database, self.seed)
        before = read_control(self.database)
        MODULE.begin_proof("mosd", self.database, self.seed)
        backup = self.database.parent / MODULE.BACKUP_NAME
        backup_bytes = backup.read_bytes()
        MODULE.set_proof_state("mosd", self.database, self.seed)

        MODULE.begin_proof("mosd", self.database, self.seed)

        self.assertEqual(backup.read_bytes(), backup_bytes)
        MODULE.restore_proof("mosd", self.database, self.seed)
        self.assertEqual(read_control(self.database), before)

    def test_proof_refuses_other_authorities_missing_backup_and_invalid_backup(self) -> None:
        MODULE.ensure_seeded("mosd", self.database, self.seed)
        for operation, authority in (
            (MODULE.begin_proof, "cra"),
            (MODULE.set_proof_state, "mosd"),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(
                    MODULE.PublisherError, MODULE.FAILURE_MESSAGE
                ):
                    operation(authority, self.database, self.seed)

        MODULE.begin_proof("mosd", self.database, self.seed)
        backup = self.database.parent / MODULE.BACKUP_NAME
        backup.chmod(0o644)
        with self.assertRaisesRegex(MODULE.PublisherError, MODULE.FAILURE_MESSAGE):
            MODULE.set_proof_state("mosd", self.database, self.seed)

        backup.chmod(0o600)
        envelope = json.loads(backup.read_text(encoding="utf-8"))
        envelope["sha256"] = "0" * 64
        backup.write_text(json.dumps(envelope), encoding="utf-8")
        backup.chmod(0o600)
        with self.assertRaisesRegex(MODULE.PublisherError, MODULE.FAILURE_MESSAGE):
            MODULE.restore_proof("mosd", self.database, self.seed)

    def test_missing_control_row_and_cli_failures_are_redacted(self) -> None:
        empty_seed = self.root / "redacted-seed" / "mosd.sqlite"
        database = self.root / "sensitive-selector-source-value" / "mosd.sqlite"
        create_mosd_database(empty_seed, include_control=False)
        MODULE.ensure_seeded("mosd", database, empty_seed)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--authority",
                "mosd",
                "--database",
                str(database),
                "--seed",
                str(empty_seed),
                "begin-proof",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), MODULE.FAILURE_MESSAGE)
        combined = result.stdout + result.stderr
        for forbidden in (
            MODULE.MOSD_CONTROL_SELECTOR,
            "sensitive-selector-source-value",
            str(database),
            str(empty_seed),
        ):
            self.assertNotIn(forbidden, combined)

    def test_cli_accepts_global_options_before_the_subcommand(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--authority",
                "mosd",
                "--database",
                str(self.database),
                "--seed",
                str(self.seed),
                "ensure-seeded",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), MODULE.SUCCESS_MESSAGE)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
