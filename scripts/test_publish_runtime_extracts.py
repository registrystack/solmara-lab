from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("publish-runtime-extracts.py")
SPEC = importlib.util.spec_from_file_location("runtime_extract_publication", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PUBLISHER = importlib.import_module("solmara_lab.publisher")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeExtractPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for authority in MODULE.AUTHORITIES:
            authored = self.root / "evidence/cells" / authority / "runtime.yaml"
            authored.parent.mkdir(parents=True)
            shutil.copy2(ROOT / "evidence/cells" / authority / "runtime.yaml", authored)
            generated = (
                self.root
                / MODULE.RUNTIME_DIRECTORY
                / authority
                / "runtime.yaml"
            )
            generated.parent.mkdir(parents=True)
            shutil.copy2(authored, generated)
            generated.chmod(0o444)
            generated.parent.chmod(0o555)

    def tearDown(self) -> None:
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_dir():
                path.chmod(0o755)
            elif path.exists():
                path.chmod(0o644)
        self.temporary.cleanup()

    def _runtime_binding(self, authority: str) -> str:
        runtime = yaml.safe_load(
            (
                self.root
                / MODULE.RUNTIME_DIRECTORY
                / authority
                / "runtime.yaml"
            ).read_text(encoding="utf-8")
        )
        profile = MODULE.AUTHORITIES[authority][0]
        return runtime["sourceExtracts"][profile]["path"]

    def _extracts(self) -> list[Path]:
        return sorted((self.root / PUBLISHER.EVIDENCE_DIRECTORY).glob("*.sqlite"))

    def _authored_digests(self) -> dict[Path, str]:
        return {
            path: digest(path)
            for path in sorted((self.root / "evidence/cells").rglob("*"))
            if path.is_file()
        }

    def test_fresh_publication_binds_only_generated_runtime_configs(self) -> None:
        authored_before = self._authored_digests()
        published_at = "2026-08-12T09:30:00.123456Z"

        result = MODULE.prepare_runtime_extracts(self.root, published_at)

        self.assertEqual(
            {authority: item["status"] for authority, item in result.items()},
            {authority: "published" for authority in MODULE.AUTHORITIES},
        )
        self.assertEqual(len(self._extracts()), 3)
        for authority, item in result.items():
            expected_id = PUBLISHER.timestamped_extract_id(authority, published_at)
            self.assertEqual(item["extractId"], expected_id)
            self.assertEqual(
                self._runtime_binding(authority),
                f"/var/lib/registry-evidence/{authority}/extracts/{expected_id}.sqlite",
            )
            extract = self.root / item["path"]
            self.assertEqual(stat.S_IMODE(extract.stat().st_mode), 0o444)
            with sqlite3.connect(extract) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT published_at, publisher, extract_id FROM evidence_extract"
                    ).fetchall(),
                    [(published_at, PUBLISHER.PUBLISHERS[authority], expected_id)],
                )
        self.assertEqual(self._authored_digests(), authored_before)

    def test_default_publication_uses_one_explicit_current_utc_time(self) -> None:
        current = "2026-08-12T09:30:00.654321Z"
        with mock.patch.object(
            MODULE, "current_publication_time", return_value=current
        ) as clock:
            result = MODULE.prepare_runtime_extracts(self.root)

        clock.assert_called_once_with()
        for authority, item in result.items():
            extract = self.root / item["path"]
            with sqlite3.connect(extract) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT published_at FROM evidence_extract"
                    ).fetchone(),
                    (current,),
                )
            self.assertEqual(
                item["extractId"],
                PUBLISHER.timestamped_extract_id(authority, current),
            )

    def test_fresh_exact_bound_extracts_are_reused(self) -> None:
        first = MODULE.prepare_runtime_extracts(
            self.root, "2026-08-12T09:00:00Z"
        )
        before = {path: digest(path) for path in self._extracts()}
        runtimes_before = {
            authority: self._runtime_binding(authority)
            for authority in MODULE.AUTHORITIES
        }

        second = MODULE.prepare_runtime_extracts(
            self.root, "2026-08-12T10:00:00Z"
        )

        self.assertEqual(
            {authority: item["status"] for authority, item in second.items()},
            {authority: "reused" for authority in MODULE.AUTHORITIES},
        )
        self.assertEqual(
            {authority: item["extractId"] for authority, item in second.items()},
            {authority: item["extractId"] for authority, item in first.items()},
        )
        self.assertEqual({path: digest(path) for path in self._extracts()}, before)
        self.assertEqual(
            {
                authority: self._runtime_binding(authority)
                for authority in MODULE.AUTHORITIES
            },
            runtimes_before,
        )

    def test_stale_extracts_are_retained_and_replaced_under_new_filenames(self) -> None:
        first = MODULE.prepare_runtime_extracts(
            self.root, "2026-08-10T09:00:00Z"
        )
        old_paths = {
            authority: self.root / item["path"]
            for authority, item in first.items()
        }
        old_digests = {authority: digest(path) for authority, path in old_paths.items()}

        second = MODULE.prepare_runtime_extracts(
            self.root, "2026-08-12T09:00:00Z"
        )

        self.assertEqual(len(self._extracts()), 6)
        for authority, item in second.items():
            self.assertEqual(item["status"], "published")
            self.assertNotEqual(item["extractId"], first[authority]["extractId"])
            self.assertTrue(old_paths[authority].exists())
            self.assertEqual(digest(old_paths[authority]), old_digests[authority])
            self.assertTrue(self._runtime_binding(authority).endswith(
                f"/{item['extractId']}.sqlite"
            ))

    def test_metadata_mismatch_fails_before_any_new_publication_or_binding(self) -> None:
        MODULE.prepare_runtime_extracts(self.root, "2026-08-12T09:00:00Z")
        cra = Path(self._runtime_binding("cra")).name
        cra_extract = self.root / PUBLISHER.EVIDENCE_DIRECTORY / cra
        cra_extract.chmod(0o644)
        with sqlite3.connect(cra_extract) as connection:
            connection.execute(
                "UPDATE evidence_extract SET publisher = ?",
                (PUBLISHER.PUBLISHERS["nia"],),
            )
            connection.commit()
        cra_extract.chmod(0o444)
        runtime_before = {
            authority: self._runtime_binding(authority)
            for authority in MODULE.AUTHORITIES
        }
        extracts_before = list(self._extracts())

        with self.assertRaisesRegex(MODULE.RuntimeExtractError, "failed validation"):
            MODULE.prepare_runtime_extracts(self.root, "2026-08-12T10:00:00Z")

        self.assertEqual(self._extracts(), extracts_before)
        self.assertEqual(
            {
                authority: self._runtime_binding(authority)
                for authority in MODULE.AUTHORITIES
            },
            runtime_before,
        )

    def test_writable_bound_extract_fails_closed(self) -> None:
        result = MODULE.prepare_runtime_extracts(
            self.root, "2026-08-12T09:00:00Z"
        )
        nia_extract = self.root / result["nia"]["path"]
        nia_extract.chmod(0o644)
        runtimes_before = {
            authority: self._runtime_binding(authority)
            for authority in MODULE.AUTHORITIES
        }

        with self.assertRaisesRegex(MODULE.RuntimeExtractError, "writable mode"):
            MODULE.prepare_runtime_extracts(self.root, "2026-08-12T10:00:00Z")

        self.assertEqual(
            {
                authority: self._runtime_binding(authority)
                for authority in MODULE.AUTHORITIES
            },
            runtimes_before,
        )

    def test_unpatchable_generated_binding_fails_before_publication(self) -> None:
        runtime = (
            self.root / MODULE.RUNTIME_DIRECTORY / "sro" / "runtime.yaml"
        )
        runtime.parent.chmod(0o755)
        runtime.chmod(0o644)
        original = runtime.read_text(encoding="utf-8")
        bound_path = self._runtime_binding("sro")
        runtime.write_text(
            original.replace(bound_path, f'"{bound_path}"'), encoding="utf-8"
        )
        runtime.chmod(0o444)
        runtime.parent.chmod(0o555)

        with self.assertRaisesRegex(MODULE.RuntimeExtractError, "uniquely patchable"):
            MODULE.prepare_runtime_extracts(self.root, "2026-08-12T09:00:00Z")

        self.assertEqual(self._extracts(), [])

    def test_cli_accepts_an_explicit_deterministic_publication_time(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--published-at",
                "2026-08-12T09:00:00Z",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(set(result), set(MODULE.AUTHORITIES))
        self.assertEqual(
            result["sro"]["extractId"], "sro-poverty-20260812T090000Z"
        )


if __name__ == "__main__":
    unittest.main()
