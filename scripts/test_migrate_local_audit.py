from __future__ import annotations

import fcntl
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_migrator():
    spec = importlib.util.spec_from_file_location(
        "migrate_local_audit", ROOT / "scripts/migrate-local-audit.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load migrate-local-audit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalAuditMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.migrator = load_migrator()

    def fixture(self, legacy_mode: str, records: int = 3):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        root.chmod(0o700)
        key = root / "audit-hmac-key"
        key.write_bytes(b"0123456789abcdef0123456789abcdef\n")
        key.chmod(0o600)
        audit = root / "audit.jsonl"
        legacy_key = key.read_bytes()
        if legacy_mode == "trim-newlines":
            legacy_key = legacy_key.rstrip(b"\r\n")
        self.write_chain(audit, legacy_key, records)
        return temporary, audit, key

    def write_chain(self, path: Path, key: bytes, records: int) -> None:
        previous = None
        lines = []
        for index in range(records):
            envelope = {
                "envelope_id": f"01TESTAUDIT{index:016d}",
                "timestamp_unix_ms": 1_700_000_000_000 + index,
                "prev_hash": previous,
                "record": {"schema": "registry.test.audit/v1", "event": index},
                "record_hash": "",
            }
            envelope["record_hash"] = self.migrator.record_hash(envelope, key)
            previous = envelope["record_hash"]
            lines.append(self.migrator.encode_json(envelope) + b"\n")
        path.write_bytes(b"".join(lines))
        path.chmod(0o600)

    def test_exact_legacy_chain_is_archived_byte_for_byte(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            before = audit.read_bytes()

            result = self.migrator.migrate(audit, key, "exact")

            archive = Path(f"{audit}{self.migrator.ARCHIVE_SUFFIX}")
            receipt = Path(f"{audit}{self.migrator.RECEIPT_SUFFIX}")
            self.assertIn("archived", result)
            self.assertFalse(audit.exists())
            self.assertEqual(archive.read_bytes(), before)
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            self.migrator.validate_archive_receipt(
                archive, receipt, "exact", key.read_bytes()
            )

    def test_trimmed_legacy_key_archives_without_changing_master_key(self) -> None:
        temporary, audit, key = self.fixture("trim-newlines")
        with temporary:
            key_before = key.read_bytes()
            self.migrator.migrate(audit, key, "trim-newlines")
            self.assertEqual(key.read_bytes(), key_before)

    def test_rerun_is_idempotent_and_revalidates_the_receipt(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            self.migrator.migrate(audit, key, "exact")
            archive = Path(f"{audit}{self.migrator.ARCHIVE_SUFFIX}")
            before = archive.read_bytes()

            result = self.migrator.migrate(audit, key, "exact")

            self.assertIn("verified archive", result)
            self.assertEqual(archive.read_bytes(), before)

    def test_unknown_or_tampered_legacy_chain_is_refused_without_archive(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            envelope = self.migrator.read_envelopes(audit)[0]
            envelope["record"]["event"] = 99
            audit.write_bytes(self.migrator.encode_json(envelope) + b"\n")
            audit.chmod(0o600)
            before = audit.read_bytes()

            with self.assertRaisesRegex(
                self.migrator.MigrationError, "expected legacy profile"
            ):
                self.migrator.migrate(audit, key, "exact")

            self.assertEqual(audit.read_bytes(), before)
            self.assertFalse(Path(f"{audit}{self.migrator.ARCHIVE_SUFFIX}").exists())

    def test_archive_tampering_is_refused_on_every_later_start(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            self.migrator.migrate(audit, key, "exact")
            archive = Path(f"{audit}{self.migrator.ARCHIVE_SUFFIX}")
            archive.write_bytes(archive.read_bytes() + b"{}\n")
            archive.chmod(0o600)

            with self.assertRaisesRegex(self.migrator.MigrationError, "no longer"):
                self.migrator.migrate(audit, key, "exact")

    def test_current_v018_chain_is_not_archived(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            derived = self.migrator.hmac.digest(
                key.read_bytes(), self.migrator.CHAIN_KEY_INFO + b"\x01", "sha256"
            )
            self.write_chain(audit, derived, 2)
            before = audit.read_bytes()

            result = self.migrator.migrate(audit, key, "exact")

            self.assertIn("verified read-only", result)
            self.assertEqual(audit.read_bytes(), before)
            self.assertFalse(Path(f"{audit}{self.migrator.ARCHIVE_SUFFIX}").exists())

    def test_running_v018_writer_is_verified_read_only(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            self.migrator.migrate(audit, key, "exact")
            derived = self.migrator.hmac.digest(
                key.read_bytes(), self.migrator.CHAIN_KEY_INFO + b"\x01", "sha256"
            )
            self.write_chain(audit, derived, 2)
            before = audit.read_bytes()

            with Path(f"{audit}.lock").open("r+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = self.migrator.migrate(audit, key, "exact")

            self.assertIn("verified read-only", result)
            self.assertEqual(audit.read_bytes(), before)

    def test_running_legacy_writer_is_refused(self) -> None:
        temporary, audit, key = self.fixture("exact")
        with temporary:
            lock_path = Path(f"{audit}.lock")
            lock_path.touch(mode=0o600)

            with lock_path.open("r+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(
                    self.migrator.MigrationError, "non-v0.18 chain"
                ):
                    self.migrator.migrate(audit, key, "exact")


if __name__ == "__main__":
    unittest.main()
