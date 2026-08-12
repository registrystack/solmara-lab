from __future__ import annotations

import hashlib
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from solmara_lab.generate import OBSERVED_AT
from solmara_lab.publisher import (
    DEFAULT_EXTRACTS,
    EVIDENCE_DIRECTORY,
    PUBLISHERS,
    RELAY_DIRECTORY,
    RELAY_FILENAMES,
    ExtractValidationError,
    StaleExtractError,
    canonical_published_at,
    mutate_mosd_state,
    publish_all,
    publish_extract,
    publish_relay_sources,
    timestamped_extract_id,
    validate_extract,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def query(path: Path, statement: str, parameters: tuple[object, ...] = ()) -> list[tuple]:
    with sqlite3.connect(path) as connection:
        return connection.execute(statement, parameters).fetchall()


def columns(path: Path, relation: str) -> list[str]:
    return [row[1] for row in query(path, f"PRAGMA table_info({relation})")]


def published_files(root: Path) -> list[Path]:
    return sorted((root / "output/sqlite").rglob("*.sqlite"))


class PublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.published = publish_all(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_repeatable_schema_content_and_bytes(self) -> None:
        relay_paths = sorted((self.root / RELAY_DIRECTORY).glob("*.sqlite"))
        before_republish = {path: digest(path) for path in relay_paths}
        publish_relay_sources(self.root)
        self.assertEqual(
            {path: digest(path) for path in relay_paths}, before_republish
        )
        with tempfile.TemporaryDirectory() as second_directory:
            second = Path(second_directory)
            publish_all(second)
            first_files = published_files(self.root)
            second_files = published_files(second)
            self.assertEqual(
                [path.relative_to(self.root) for path in first_files],
                [path.relative_to(second) for path in second_files],
            )
            self.assertEqual(
                [digest(path) for path in first_files],
                [digest(path) for path in second_files],
            )

    def test_relay_views_have_stable_record_fields_and_minimal_domains(self) -> None:
        required = [
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
        ]
        expected = {
            "cra": {
                "relay_civil_person": required
                + ["uin", "birth_date", "birth_brn", "deceased"]
            },
            "nia": {
                "relay_population_person": required
                + [
                    "uin",
                    "legacy_nid",
                    "given_name",
                    "family_name",
                    "sex",
                    "birth_date",
                    "identity_status",
                    "alive",
                ]
            },
            "mosd": {
                "relay_beneficiary_enrolment": required + ["uin", "duplicate_flag"]
            },
            "sipf": {
                "relay_pension_payment": required + ["pensioner_uin", "payment_status"],
                "relay_survivor_case": required + ["spouse_uin", "survivor_eligible"],
            },
            "nagdi": {
                "relay_farmer_voucher": required
                + [
                    "farmer_id",
                    "farmer_registered",
                    "data_use_authorized",
                    "active_smallholder_farmer",
                    "active_farm_parcel",
                    "crop_declared_for_season",
                    "district_climate_risk_active",
                    "voucher_entitlement_current",
                    "voucher_not_redeemed",
                ],
                "relay_livestock_movement": required
                + [
                    "herd_id",
                    "farmer_id",
                    "registered_herd",
                    "herd_vaccination_current",
                    "origin_district_not_quarantined_for_species",
                    "destination_district_open",
                    "no_conflicting_open_movement_permit",
                ],
            },
        }
        for authority, relations in expected.items():
            path = self.root / RELAY_DIRECTORY / RELAY_FILENAMES[authority]
            for relation, expected_columns in relations.items():
                self.assertEqual(columns(path, relation), expected_columns)
                record_fields = query(
                    path,
                    f"SELECT record_id, record_revision, lifecycle_state, recorded_at FROM {relation}",
                )
                self.assertTrue(record_fields)
                self.assertTrue(all(all(value for value in row) for row in record_fields))

    def test_expected_positive_and_control_rows_are_preserved(self) -> None:
        cra = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["cra"]
        self.assertEqual(
            query(
                cra,
                "SELECT birth_brn, deceased FROM relay_civil_person WHERE uin = ?",
                ("2300010248",),
            ),
            [("BRN-2022-0101-00001", 0)],
        )
        self.assertEqual(
            query(
                cra,
                "SELECT deceased FROM relay_civil_person WHERE uin = ?",
                ("2300109568",),
            ),
            [(1,)],
        )

        nia = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["nia"]
        self.assertEqual(
            query(
                nia,
                "SELECT identity_status, alive, recorded_at FROM relay_population_person WHERE uin = ?",
                ("2300127827",),
            ),
            [("active", 1, "2026-07-01T08:00:00Z")],
        )
        self.assertEqual(
            query(
                nia,
                "SELECT identity_status, alive FROM relay_population_person WHERE uin = ?",
                ("2300109568",),
            ),
            [("deceased", 0)],
        )

        mosd = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["mosd"]
        self.assertEqual(
            query(
                mosd,
                "SELECT uin, duplicate_flag FROM relay_beneficiary_enrolment WHERE uin IN (?, ?) ORDER BY uin",
                ("2300010248", "2300054788"),
            ),
            [("2300010248", 0), ("2300054788", 1)],
        )

        sipf = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["sipf"]
        self.assertEqual(
            query(
                sipf,
                "SELECT payment_status FROM relay_pension_payment WHERE pensioner_uin = ?",
                ("2300109568",),
            ),
            [("active",)],
        )
        self.assertEqual(
            query(
                sipf,
                "SELECT survivor_eligible FROM relay_survivor_case WHERE spouse_uin = ?",
                ("2300146081",),
            ),
            [(0,)],
        )

        nagdi = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["nagdi"]
        self.assertEqual(
            query(
                nagdi,
                "SELECT data_use_authorized FROM relay_farmer_voucher WHERE farmer_id = ?",
                ("FR-1002",),
            ),
            [(0,)],
        )
        self.assertEqual(
            query(
                nagdi,
                "SELECT origin_district_not_quarantined_for_species FROM relay_livestock_movement WHERE farmer_id = ?",
                ("FR-1004",),
            ),
            [(0,)],
        )

    def test_extract_metadata_is_exact_and_no_sidecars_remain(self) -> None:
        table_by_authority = {
            "cra": "birth_evidence",
            "nia": "population_evidence",
            "sro": "poverty_evidence",
        }
        for authority, extract_id in DEFAULT_EXTRACTS.items():
            path = self.root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
            self.assertEqual(
                query(path, "SELECT published_at, publisher, extract_id FROM evidence_extract"),
                [(OBSERVED_AT, PUBLISHERS[authority], extract_id)],
            )
            self.assertEqual(
                query(path, "SELECT count(*) FROM evidence_extract"), [(1,)]
            )
            self.assertTrue(query(path, f"SELECT record_id FROM {table_by_authority[authority]} LIMIT 1"))
        for path in published_files(self.root):
            for suffix in ("-journal", "-shm", "-wal"):
                self.assertFalse(path.with_name(path.name + suffix).exists())
        for extract_id in DEFAULT_EXTRACTS.values():
            path = self.root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_extract_tables_have_only_the_required_columns(self) -> None:
        required = [
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
        ]
        expected = {
            "cra": ("birth_evidence", required + ["uin", "birth_date", "birth_brn"]),
            "nia": (
                "population_evidence",
                required
                + [
                    "uin",
                    "identity_status",
                    "alive",
                ],
            ),
            "sro": ("poverty_evidence", required + ["uin", "poverty_band"]),
        }
        for authority, (table, expected_columns) in expected.items():
            extract_id = DEFAULT_EXTRACTS[authority]
            path = self.root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
            self.assertEqual(columns(path, table), expected_columns)

    def test_extract_rows_keep_birth_population_and_poverty_story_outcomes(self) -> None:
        cra = self.root / EVIDENCE_DIRECTORY / f"{DEFAULT_EXTRACTS['cra']}.sqlite"
        self.assertEqual(
            query(
                cra,
                "SELECT birth_brn, lifecycle_state FROM birth_evidence WHERE uin = ?",
                ("2300010248",),
            ),
            [("BRN-2022-0101-00001", "registered")],
        )
        self.assertEqual(
            query(
                cra,
                "SELECT birth_date, birth_brn, lifecycle_state FROM birth_evidence WHERE uin = ?",
                ("2300073046",),
            ),
            [("2020-05-18", None, "unregistered")],
        )
        self.assertEqual(
            query(
                cra,
                "SELECT birth_date, birth_brn, lifecycle_state FROM birth_evidence WHERE uin = ?",
                ("2300091305",),
            ),
            [("2019-12-12", "BRN-2019-0203-00010", "registered")],
        )

        nia = self.root / EVIDENCE_DIRECTORY / f"{DEFAULT_EXTRACTS['nia']}.sqlite"
        self.assertEqual(
            query(
                nia,
                "SELECT identity_status, alive FROM population_evidence WHERE uin = ?",
                ("2300109568",),
            ),
            [("deceased", 0)],
        )

        sro = self.root / EVIDENCE_DIRECTORY / f"{DEFAULT_EXTRACTS['sro']}.sqlite"
        self.assertEqual(
            query(
                sro,
                "SELECT uin, poverty_band FROM poverty_evidence WHERE uin IN (?, ?) ORDER BY uin",
                ("2300010248", "2300036523"),
            ),
            [("2300010248", "priority"), ("2300036523", "not_eligible")],
        )

    def test_immutable_extract_refuses_an_existing_target(self) -> None:
        extract_id = "sro-poverty-20260705T090000Z"
        publish_extract(self.root, "sro", "2026-07-05T09:00:00Z", extract_id)
        with self.assertRaises(FileExistsError):
            publish_extract(self.root, "sro", "2026-07-05T09:00:00Z", extract_id)

    def test_extract_refuses_a_non_rfc3339_publication_time(self) -> None:
        for suffix, published_at in (
            ("syntax", "2026-07-05 09:00:00"),
            ("calendar", "2026-02-30T09:00:00Z"),
        ):
            with self.subTest(published_at=published_at):
                extract_id = f"sro-poverty-invalid-{suffix}"
                with self.assertRaisesRegex(ValueError, "RFC 3339"):
                    publish_extract(self.root, "sro", published_at, extract_id)
                self.assertFalse(
                    (self.root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite").exists()
                )

    def test_a_second_sro_publication_uses_a_new_filename(self) -> None:
        original = self.root / EVIDENCE_DIRECTORY / f"{DEFAULT_EXTRACTS['sro']}.sqlite"
        original_digest = digest(original)
        extract_id = "sro-poverty-20260705T090000Z"
        second = publish_extract(
            self.root, "sro", "2026-07-05T09:00:00Z", extract_id
        )
        self.assertNotEqual(original, second)
        self.assertEqual(digest(original), original_digest)
        self.assertEqual(
            query(second, "SELECT published_at, publisher, extract_id FROM evidence_extract"),
            [("2026-07-05T09:00:00Z", PUBLISHERS["sro"], extract_id)],
        )

    def test_timestamped_extract_ids_are_deterministic_for_the_instant(self) -> None:
        self.assertEqual(
            canonical_published_at("2026-08-12T16:34:56.123456+07:00"),
            "2026-08-12T09:34:56.123456Z",
        )
        self.assertEqual(
            timestamped_extract_id("cra", "2026-08-12T16:34:56.123456+07:00"),
            "cra-birth-20260812T093456123456Z",
        )
        self.assertEqual(
            timestamped_extract_id("cra", "2026-08-12T09:34:56.123456Z"),
            "cra-birth-20260812T093456123456Z",
        )

    def test_extract_validation_binds_exact_metadata_schema_and_age(self) -> None:
        extract_id = "sro-poverty-20260812T090000Z"
        path = publish_extract(
            self.root, "sro", "2026-08-12T09:00:00Z", extract_id
        )
        metadata = validate_extract(
            path,
            "sro",
            observed_at="2026-08-12T10:00:00Z",
            expected_extract_id=extract_id,
            expected_published_at="2026-08-12T09:00:00Z",
        )
        self.assertEqual(metadata.extract_id, extract_id)
        with self.assertRaisesRegex(StaleExtractError, "accepted age"):
            validate_extract(
                path,
                "sro",
                observed_at="2026-08-13T09:00:01Z",
                expected_extract_id=extract_id,
            )
        with self.assertRaisesRegex(ExtractValidationError, "future"):
            validate_extract(
                path,
                "sro",
                observed_at="2026-08-12T08:59:59Z",
                expected_extract_id=extract_id,
            )

        path.chmod(0o644)
        try:
            with self.assertRaisesRegex(ExtractValidationError, "writable"):
                validate_extract(
                    path,
                    "sro",
                    observed_at="2026-08-12T10:00:00Z",
                    expected_extract_id=extract_id,
                )
        finally:
            path.chmod(0o444)

    def test_extract_validation_refuses_metadata_mismatch_and_extra_columns(self) -> None:
        cases = ("publisher", "extract_id", "column", "row")
        for index, mismatch in enumerate(cases):
            with self.subTest(mismatch=mismatch):
                extract_id = f"sro-poverty-20260812T10000{index}Z"
                path = publish_extract(
                    self.root, "sro", "2026-08-12T10:00:00Z", extract_id
                )
                path.chmod(0o644)
                with sqlite3.connect(path) as connection:
                    if mismatch == "publisher":
                        connection.execute(
                            "UPDATE evidence_extract SET publisher = ?",
                            (PUBLISHERS["cra"],),
                        )
                    elif mismatch == "extract_id":
                        connection.execute(
                            "UPDATE evidence_extract SET extract_id = ?",
                            ("metadata-does-not-match",),
                        )
                    elif mismatch == "column":
                        connection.execute(
                            "ALTER TABLE evidence_extract ADD COLUMN unexpected TEXT"
                        )
                    else:
                        connection.execute(
                            "INSERT INTO evidence_extract VALUES (?, ?, ?)",
                            (
                                "2026-08-12T10:00:00Z",
                                PUBLISHERS["sro"],
                                extract_id,
                            ),
                        )
                    connection.commit()
                path.chmod(0o444)
                with self.assertRaises(ExtractValidationError):
                    validate_extract(
                        path,
                        "sro",
                        observed_at="2026-08-12T10:00:00Z",
                        expected_extract_id=extract_id,
                    )

    def test_mosd_mutation_changes_only_the_live_source_in_place(self) -> None:
        files = published_files(self.root)
        before_digests = {path: digest(path) for path in files}
        mosd = self.root / RELAY_DIRECTORY / RELAY_FILENAMES["mosd"]
        before_inode = mosd.stat().st_ino
        before_row = query(
            mosd,
            "SELECT * FROM relay_beneficiary_enrolment WHERE uin = ?",
            ("2300010248",),
        )[0]

        mutate_mosd_state(mosd, "2300010248", True, "2026-07-05T10:00:00Z")

        after_row = query(
            mosd,
            "SELECT * FROM relay_beneficiary_enrolment WHERE uin = ?",
            ("2300010248",),
        )[0]
        changed = {path for path in files if digest(path) != before_digests[path]}
        self.assertEqual(changed, {mosd})
        self.assertEqual(mosd.stat().st_ino, before_inode)
        self.assertEqual(before_row[0], after_row[0])
        self.assertNotEqual(before_row[1], after_row[1])
        self.assertEqual(after_row[2], "active")
        self.assertEqual(after_row[3], "2026-07-05T10:00:00Z")
        self.assertEqual(after_row[4], "2300010248")
        self.assertEqual((before_row[5], after_row[5]), (0, 1))
        for suffix in ("-journal", "-shm", "-wal"):
            self.assertFalse(mosd.with_name(mosd.name + suffix).exists())

    def test_module_cli_publishes_and_mutates(self) -> None:
        with tempfile.TemporaryDirectory() as cli_directory:
            cli_root = Path(cli_directory)
            publish = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "solmara_lab.publisher",
                    "publish-all",
                    "--root",
                    str(cli_root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(publish.returncode, 0, publish.stderr)
            mosd = cli_root / RELAY_DIRECTORY / RELAY_FILENAMES["mosd"]
            mutation = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "solmara_lab.publisher",
                    "mutate-mosd",
                    "--root",
                    str(cli_root),
                    "--uin",
                    "2300010248",
                    "--duplicate-flag",
                    "true",
                    "--recorded-at",
                    "2026-07-05T10:00:00Z",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(mutation.returncode, 0, mutation.stderr)
            self.assertEqual(
                query(
                    mosd,
                    "SELECT duplicate_flag, recorded_at FROM relay_beneficiary_enrolment WHERE uin = ?",
                    ("2300010248",),
                ),
                [(1, "2026-07-05T10:00:00Z")],
            )
            extract_id = "sro-poverty-20260705T110000Z"
            extract = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "solmara_lab.publisher",
                    "publish-extract",
                    "--root",
                    str(cli_root),
                    "--authority",
                    "sro",
                    "--published-at",
                    "2026-07-05T11:00:00Z",
                    "--extract-id",
                    extract_id,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(extract.returncode, 0, extract.stderr)
            extract_path = cli_root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
            self.assertEqual(
                query(extract_path, "SELECT published_at, publisher, extract_id FROM evidence_extract"),
                [("2026-07-05T11:00:00Z", PUBLISHERS["sro"], extract_id)],
            )
            self.assertEqual(stat.S_IMODE(extract_path.stat().st_mode), 0o444)


if __name__ == "__main__":
    unittest.main()
