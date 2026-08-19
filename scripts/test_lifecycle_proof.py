from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).with_name("lifecycle_proof.py")
SPEC = importlib.util.spec_from_file_location("lifecycle_proof", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)


class LifecycleProofTests(unittest.TestCase):
    def test_complete_proof_is_isolated_and_passes_every_check(self) -> None:
        result = lifecycle.run_proof()

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["fixtureState"], "isolated-temporary-directory")
        self.assertTrue(all(result["checks"].values()))

    def test_long_lived_read_only_mosd_binding_observes_in_place_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lifecycle.publish_all(root)
            database = (
                root
                / lifecycle.RELAY_DIRECTORY
                / lifecycle.RELAY_FILENAMES["mosd"]
            )
            inode = database.stat().st_ino
            binding = lifecycle.GovernedMosdObservation(database)
            try:
                connection_id = id(binding.connection)
                before = binding.observe_duplicate_flag(lifecycle.MOSD_TEST_UIN)
                lifecycle.mutate_mosd_state(
                    database,
                    lifecycle.MOSD_TEST_UIN,
                    True,
                    "2026-07-05T08:15:00Z",
                )
                after = binding.observe_duplicate_flag(lifecycle.MOSD_TEST_UIN)
            finally:
                binding.close()

            self.assertEqual((before[0], after[0]), (0, 1))
            self.assertNotEqual(before[1:], after[1:])
            self.assertEqual(database.stat().st_ino, inode)
            self.assertEqual(id(binding.connection), connection_id)

    def test_sro_binding_requires_explicit_rebind_to_changed_extract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lifecycle.publish_all(root)
            observed_at = datetime(2026, 7, 5, 8, 30, tzinfo=timezone.utc)
            original_id = lifecycle.DEFAULT_EXTRACTS["sro"]
            original = (
                root / lifecycle.EVIDENCE_DIRECTORY / f"{original_id}.sqlite"
            )
            original_digest = hashlib.sha256(original.read_bytes()).hexdigest()
            binding = lifecycle.SroExtractBinding(
                original,
                expected_extract_id=original_id,
                observed_at=observed_at,
            )
            replacement_id = "sro-poverty-20260705T080000Z"
            replacement = lifecycle._publish_changed_sro_extract(
                root,
                extract_id=replacement_id,
                published_at="2026-07-05T08:00:00Z",
                poverty_band="not_eligible",
            )
            try:
                still_old = binding.observe_poverty_band(lifecycle.SRO_TEST_UIN)
            finally:
                binding.close()

            rebound = lifecycle.SroExtractBinding(
                replacement,
                expected_extract_id=replacement_id,
                observed_at=observed_at,
            )
            try:
                changed = rebound.observe_poverty_band(lifecycle.SRO_TEST_UIN)
            finally:
                rebound.close()

            self.assertNotEqual(still_old, changed)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), original_digest)
            self.assertNotEqual(original, replacement)

    def test_invalid_stale_and_writable_extracts_fail_closed(self) -> None:
        observed_at = datetime(2026, 7, 5, 8, 30, tzinfo=timezone.utc)
        cases = (
            ("stale", "2026-07-03T08:00:00Z", None, False),
            (
                "metadata",
                "2026-07-05T08:00:00Z",
                "metadata-does-not-match-binding",
                False,
            ),
            ("writable", "2026-07-05T08:00:00Z", None, True),
        )
        for suffix, published_at, metadata_id, make_writable in cases:
            with self.subTest(case=suffix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                lifecycle.publish_all(root)
                extract_id = f"sro-poverty-20260705T08-{suffix}"
                extract = lifecycle._publish_changed_sro_extract(
                    root,
                    extract_id=extract_id,
                    published_at=published_at,
                    poverty_band="not_eligible",
                    metadata_extract_id=metadata_id,
                )
                if make_writable:
                    extract.chmod(0o644)
                with self.assertRaises(lifecycle.LifecycleProofError):
                    lifecycle.SroExtractBinding(
                        extract,
                        expected_extract_id=extract_id,
                        observed_at=observed_at,
                    )

    def test_immutable_publication_refuses_overwrite_without_changing_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lifecycle.publish_all(root)
            extract_id = lifecycle.DEFAULT_EXTRACTS["sro"]
            extract = root / lifecycle.EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
            before = hashlib.sha256(extract.read_bytes()).digest()
            with self.assertRaises(FileExistsError):
                lifecycle.publish_extract(
                    root,
                    "sro",
                    "2026-07-05T08:00:00Z",
                    extract_id,
                )
            self.assertEqual(hashlib.sha256(extract.read_bytes()).digest(), before)
            self.assertEqual(stat.S_IMODE(extract.stat().st_mode), 0o444)

    def test_json_cli_emits_only_sanitized_proof_state(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "pass")
        serialized = completed.stdout.lower()
        for forbidden in (
            lifecycle.MOSD_TEST_UIN,
            lifecycle.SRO_TEST_UIN,
            "poverty_band",
            "record_revision",
            "sqlite",
        ):
            self.assertNotIn(forbidden.lower(), serialized)


if __name__ == "__main__":
    unittest.main()
