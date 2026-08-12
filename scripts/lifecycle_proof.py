#!/usr/bin/env python3
"""Prove the two Solmara publisher cadences without touching active data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generator"))

from solmara_lab.publisher import (  # noqa: E402
    DEFAULT_EXTRACTS,
    EVIDENCE_DIRECTORY,
    PUBLISHERS,
    RELAY_DIRECTORY,
    RELAY_FILENAMES,
    mutate_mosd_state,
    publish_all,
    publish_extract,
)

MAX_EXTRACT_AGE = timedelta(seconds=86_400)
MOSD_TEST_UIN = "2300010248"
SRO_TEST_UIN = "2300010248"


class LifecycleProofError(RuntimeError):
    """Raised when a lifecycle invariant is not demonstrated."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


class GovernedMosdObservation:
    """A long-lived, read-only source binding like Relay's mounted source."""

    def __init__(self, database: Path) -> None:
        self.database = database.resolve()
        self.connection = sqlite3.connect(_database_uri(self.database), uri=True)

    def close(self) -> None:
        self.connection.close()

    def observe_duplicate_flag(self, uin: str) -> tuple[int, str, str]:
        row = self.connection.execute(
            """
            SELECT duplicate_flag, record_revision, recorded_at
            FROM relay_beneficiary_enrolment
            WHERE uin = ?
            """,
            (uin,),
        ).fetchone()
        if row is None:
            raise LifecycleProofError("governed MoSD lookup did not resolve exactly once")
        return int(row[0]), str(row[1]), str(row[2])


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise LifecycleProofError("extract timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_sro_extract(
    path: Path,
    *,
    expected_extract_id: str,
    observed_at: datetime,
) -> None:
    if path.name != f"{expected_extract_id}.sqlite":
        raise LifecycleProofError("extract filename does not match its binding")
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        raise LifecycleProofError("extract has a writable mode")

    with sqlite3.connect(_database_uri(path), uri=True) as connection:
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise LifecycleProofError("extract integrity check failed")
        metadata = connection.execute(
            "SELECT published_at, publisher, extract_id FROM evidence_extract"
        ).fetchall()
        if len(metadata) != 1:
            raise LifecycleProofError("extract metadata cardinality is invalid")
        published_at, publisher, extract_id = metadata[0]
        if publisher != PUBLISHERS["sro"] or extract_id != expected_extract_id:
            raise LifecycleProofError("extract metadata does not match its binding")
        published = _parse_timestamp(str(published_at))
        age = observed_at.astimezone(timezone.utc) - published
        if age < timedelta(0) or age > MAX_EXTRACT_AGE:
            raise LifecycleProofError("extract is outside its accepted age")

        expected_columns = [
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "poverty_band",
        ]
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(poverty_evidence)")
        ]
        if columns != expected_columns:
            raise LifecycleProofError("extract schema does not match the SRO contract")


class SroExtractBinding:
    """An Evidence-cell binding fixed to one immutable extract filename."""

    def __init__(
        self,
        path: Path,
        *,
        expected_extract_id: str,
        observed_at: datetime,
    ) -> None:
        self.path = path.resolve()
        self.expected_extract_id = expected_extract_id
        _validate_sro_extract(
            self.path,
            expected_extract_id=expected_extract_id,
            observed_at=observed_at,
        )
        self.connection = sqlite3.connect(_database_uri(self.path), uri=True)

    def close(self) -> None:
        self.connection.close()

    def observe_poverty_band(self, uin: str) -> str:
        row = self.connection.execute(
            "SELECT poverty_band FROM poverty_evidence WHERE uin = ?", (uin,)
        ).fetchone()
        if row is None:
            raise LifecycleProofError("bound SRO extract did not resolve exactly once")
        return str(row[0])


def _revision(
    *,
    record_id: str,
    lifecycle_state: str,
    recorded_at: str,
    uin: str,
    poverty_band: str,
) -> str:
    value = {
        "record_id": record_id,
        "lifecycle_state": lifecycle_state,
        "recorded_at": recorded_at,
        "uin": uin,
        "poverty_band": poverty_band,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"rev-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _publish_changed_sro_extract(
    root: Path,
    *,
    extract_id: str,
    published_at: str,
    poverty_band: str,
    metadata_extract_id: str | None = None,
) -> Path:
    """Stage changes before atomically publishing a never-before-used filename."""

    staging_root = root / ".lifecycle-staging" / extract_id
    staged = publish_extract(staging_root, "sro", published_at, extract_id)
    staged.chmod(0o600)
    with sqlite3.connect(staged) as connection:
        current = connection.execute(
            """
            SELECT record_id, lifecycle_state, recorded_at
            FROM poverty_evidence
            WHERE uin = ?
            """,
            (SRO_TEST_UIN,),
        ).fetchone()
        if current is None:
            raise LifecycleProofError("staged SRO extract is missing its control row")
        connection.execute(
            """
            UPDATE poverty_evidence
            SET poverty_band = ?, record_revision = ?
            WHERE uin = ?
            """,
            (
                poverty_band,
                _revision(
                    record_id=str(current[0]),
                    lifecycle_state=str(current[1]),
                    recorded_at=str(current[2]),
                    uin=SRO_TEST_UIN,
                    poverty_band=poverty_band,
                ),
                SRO_TEST_UIN,
            ),
        )
        if metadata_extract_id is not None:
            connection.execute(
                "UPDATE evidence_extract SET extract_id = ?", (metadata_extract_id,)
            )
        connection.commit()
        connection.execute("VACUUM")
    staged.chmod(0o444)

    target = root / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(staged, target)
    except FileExistsError:
        raise LifecycleProofError("immutable extract publication refused overwrite") from None
    return target


def run_proof() -> dict[str, object]:
    reference_time = datetime(2026, 7, 5, 8, 30, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory(prefix="solmara-lifecycle-") as temporary:
        root = Path(temporary)
        publish_all(root)

        mosd = root / RELAY_DIRECTORY / RELAY_FILENAMES["mosd"]
        mosd_inode = (mosd.stat().st_dev, mosd.stat().st_ino)
        mosd_binding = GovernedMosdObservation(mosd)
        try:
            connection_identity = id(mosd_binding.connection)
            before = mosd_binding.observe_duplicate_flag(MOSD_TEST_UIN)
            mutate_mosd_state(
                mosd,
                MOSD_TEST_UIN,
                True,
                "2026-07-05T08:15:00Z",
            )
            after = mosd_binding.observe_duplicate_flag(MOSD_TEST_UIN)
            if (before[0], after[0]) != (0, 1):
                raise LifecycleProofError("live MoSD state did not change on next observation")
            if before[1] == after[1] or before[2] == after[2]:
                raise LifecycleProofError("live MoSD revision metadata did not advance")
            if (mosd.stat().st_dev, mosd.stat().st_ino) != mosd_inode:
                raise LifecycleProofError("live MoSD mutation replaced the mounted inode")
            if id(mosd_binding.connection) != connection_identity:
                raise LifecycleProofError("live MoSD source binding was restarted")
        finally:
            mosd_binding.close()

        original_id = DEFAULT_EXTRACTS["sro"]
        original = root / EVIDENCE_DIRECTORY / f"{original_id}.sqlite"
        original_digest = _digest(original)
        original_inode = (original.stat().st_dev, original.stat().st_ino)
        old_binding = SroExtractBinding(
            original,
            expected_extract_id=original_id,
            observed_at=reference_time,
        )
        replacement_id = "sro-poverty-20260705T080000Z"
        replacement = _publish_changed_sro_extract(
            root,
            extract_id=replacement_id,
            published_at="2026-07-05T08:00:00Z",
            poverty_band="not_eligible",
        )
        try:
            old_result_before = old_binding.observe_poverty_band(SRO_TEST_UIN)
            old_result_after_publication = old_binding.observe_poverty_band(SRO_TEST_UIN)
            if old_result_before != old_result_after_publication:
                raise LifecycleProofError("active SRO binding changed before a restart")
            if _digest(original) != original_digest:
                raise LifecycleProofError("active immutable SRO extract was overwritten")
            if (original.stat().st_dev, original.stat().st_ino) != original_inode:
                raise LifecycleProofError("active immutable SRO extract was replaced")
            try:
                publish_extract(root, "sro", "2026-07-05T08:00:00Z", original_id)
            except FileExistsError:
                pass
            else:
                raise LifecycleProofError("publisher allowed an active extract overwrite")
        finally:
            old_binding.close()

        rebound = SroExtractBinding(
            replacement,
            expected_extract_id=replacement_id,
            observed_at=reference_time,
        )
        try:
            rebound_result = rebound.observe_poverty_band(SRO_TEST_UIN)
        finally:
            rebound.close()
        if rebound_result == old_result_after_publication:
            raise LifecycleProofError("SRO-only rebind did not expose the new assertion input")

        stale_id = "sro-poverty-20260703T080000Z"
        stale = _publish_changed_sro_extract(
            root,
            extract_id=stale_id,
            published_at="2026-07-03T08:00:00Z",
            poverty_band="not_eligible",
        )
        try:
            SroExtractBinding(
                stale,
                expected_extract_id=stale_id,
                observed_at=reference_time,
            )
        except LifecycleProofError:
            pass
        else:
            raise LifecycleProofError("stale SRO extract did not fail closed")

        invalid_id = "sro-poverty-20260705T081000Z"
        invalid = _publish_changed_sro_extract(
            root,
            extract_id=invalid_id,
            published_at="2026-07-05T08:10:00Z",
            poverty_band="not_eligible",
            metadata_extract_id="metadata-does-not-match-binding",
        )
        try:
            SroExtractBinding(
                invalid,
                expected_extract_id=invalid_id,
                observed_at=reference_time,
            )
        except LifecycleProofError:
            pass
        else:
            raise LifecycleProofError("invalid SRO extract did not fail closed")

        return {
            "status": "pass",
            "fixtureState": "isolated-temporary-directory",
            "checks": {
                "mosdInPlaceMutationVisibleWithoutRestart": True,
                "sroNewFilenameRequired": True,
                "sroOldBindingStableUntilRebind": True,
                "activeExtractOverwriteDenied": True,
                "staleReplacementDenied": True,
                "invalidReplacementDenied": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the sanitized result as compact JSON",
    )
    args = parser.parse_args()
    result = run_proof()
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print("Solmara lifecycle proof: PASS")
        for check in result["checks"]:
            print(f"- {check}: PASS")
        print("- fixtureState: isolated temporary directory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
