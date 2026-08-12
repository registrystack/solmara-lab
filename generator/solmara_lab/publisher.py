from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

from .generate import OBSERVED_AT, build_relay_projections, build_rows

RELAY_DIRECTORY = Path("output/sqlite/relay")
EVIDENCE_DIRECTORY = Path("output/sqlite/evidence")

RELAY_FILENAMES = {
    "cra": "cra.sqlite",
    "nia": "nia.sqlite",
    "mosd": "mosd.sqlite",
    "sipf": "sipf.sqlite",
    "nagdi": "nagdi.sqlite",
}

DEFAULT_EXTRACTS = {
    "cra": "cra-birth-20260704T090000Z",
    "nia": "nia-population-20260704T090000Z",
    "sro": "sro-poverty-20260704T090000Z",
}

PUBLISHERS = {
    "cra": "did:web:id.registrystack.org:solmara:authority:cra",
    "nia": "did:web:id.registrystack.org:solmara:authority:nia",
    "sro": "did:web:id.registrystack.org:solmara:authority:sro",
}

EXTRACT_PREFIXES = {
    "cra": "cra-birth",
    "nia": "nia-population",
    "sro": "sro-poverty",
}

MAX_EXTRACT_AGE_SECONDS = 86_400

EXTRACT_TABLES = {
    "cra": (
        "birth_evidence",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "birth_date",
            "birth_brn",
        ),
    ),
    "nia": (
        "population_evidence",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "identity_status",
            "alive",
        ),
    ),
    "sro": (
        "poverty_evidence",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "poverty_band",
        ),
    ),
}

_EXTRACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)


class ExtractValidationError(RuntimeError):
    """Raised when an immutable extract cannot be trusted for binding."""


class StaleExtractError(ExtractValidationError):
    """Raised when an otherwise valid extract is outside its accepted age."""


class ExtractMetadata(NamedTuple):
    published_at: str
    publisher: str
    extract_id: str


def _bool(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if str(value).lower() == "true":
        return 1
    if str(value).lower() == "false":
        return 0
    raise ValueError("expected a boolean value")


def _revision(record: dict[str, object]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return f"rev-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _record(
    record_id: object,
    lifecycle_state: object,
    recorded_at: object,
    **domain: object,
) -> tuple[object, ...]:
    revision_input = {
        "record_id": str(record_id),
        "lifecycle_state": str(lifecycle_state),
        "recorded_at": str(recorded_at),
        **domain,
    }
    return (
        str(record_id),
        _revision(revision_input),
        str(lifecycle_state),
        str(recorded_at),
        *domain.values(),
    )


def _configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA secure_delete = ON")
    connection.execute("PRAGMA user_version = 1")


def _finish(connection: sqlite3.Connection) -> None:
    connection.commit()
    connection.execute("VACUUM")
    connection.execute("PRAGMA optimize")


def _sidecars(path: Path) -> list[Path]:
    candidates = [
        path.with_name(path.name + suffix)
        for suffix in ("-journal", "-shm", "-wal")
    ]
    return [candidate for candidate in candidates if candidate.exists()]


def _ensure_no_sidecars(path: Path) -> None:
    if _sidecars(path):
        raise RuntimeError("SQLite publication left a journal sidecar")


def _replace_database(
    target: Path, populate: Callable[[sqlite3.Connection], None]
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with sqlite3.connect(temporary) as connection:
            _configure(connection)
            populate(connection)
            _finish(connection)
        _ensure_no_sidecars(temporary)
        os.replace(temporary, target)
        _ensure_no_sidecars(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _create_immutable_database(
    target: Path, populate: Callable[[sqlite3.Connection], None]
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError("immutable Evidence extract target already exists") from None
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with sqlite3.connect(temporary) as connection:
            _configure(connection)
            populate(connection)
            _finish(connection)
        _ensure_no_sidecars(temporary)
        temporary.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise FileExistsError(
                "immutable Evidence extract target already exists"
            ) from None
        _ensure_no_sidecars(target)
    finally:
        temporary.unlink(missing_ok=True)
        for sidecar in _sidecars(temporary):
            sidecar.unlink()


def _insert_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> None:
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        rows,
    )


def _publisher_rows(root: Path) -> dict[str, list[dict[str, object]]]:
    rows = build_rows(root)
    rows.update(build_relay_projections(rows))
    return rows


def _publish_cra(connection: sqlite3.Connection, rows: dict[str, list[dict[str, object]]]) -> None:
    connection.executescript(
        """
        CREATE TABLE civil_person_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            uin TEXT NOT NULL UNIQUE,
            birth_date TEXT NOT NULL,
            birth_brn TEXT,
            deceased INTEGER NOT NULL CHECK (deceased IN (0, 1))
        ) STRICT;
        CREATE VIEW relay_civil_person AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               uin, birth_date, birth_brn, deceased
        FROM civil_person_source;
        """
    )
    people = {row["uin"]: row for row in rows["civil_person"]}
    records = []
    for row in rows["civil_person_projection"]:
        person = people[row["uin"]]
        records.append(
            _record(
                person["person_id"],
                "deceased" if _bool(row["deceased"]) else "active",
                person["observed_at"],
                uin=row["uin"],
                birth_date=row["birth_date"],
                birth_brn=row["birth_brn"] or None,
                deceased=_bool(row["deceased"]),
            )
        )
    _insert_rows(
        connection,
        "civil_person_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "birth_date",
            "birth_brn",
            "deceased",
        ),
        records,
    )


def _publish_nia(connection: sqlite3.Connection, rows: dict[str, list[dict[str, object]]]) -> None:
    connection.executescript(
        """
        CREATE TABLE population_person_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            uin TEXT NOT NULL UNIQUE,
            legacy_nid TEXT,
            given_name TEXT NOT NULL,
            family_name TEXT NOT NULL,
            sex TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            identity_status TEXT NOT NULL,
            alive INTEGER NOT NULL CHECK (alive IN (0, 1))
        ) STRICT;
        CREATE VIEW relay_population_person AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               uin, legacy_nid, given_name, family_name, sex, birth_date,
               identity_status, alive
        FROM population_person_source;
        """
    )
    records = [
        _record(
            row["person_id"],
            row["identity_status"],
            row["updated_at"],
            uin=row["uin"],
            legacy_nid=row["legacy_nid"] or None,
            given_name=row["given_name"],
            family_name=row["family_name"],
            sex=row["sex"],
            birth_date=row["birth_date"],
            identity_status=row["identity_status"],
            alive=_bool(row["alive"]),
        )
        for row in rows["population_person"]
    ]
    _insert_rows(
        connection,
        "population_person_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "legacy_nid",
            "given_name",
            "family_name",
            "sex",
            "birth_date",
            "identity_status",
            "alive",
        ),
        records,
    )


def _publish_mosd(connection: sqlite3.Connection, rows: dict[str, list[dict[str, object]]]) -> None:
    connection.executescript(
        """
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
    records = [
        _record(
            f"MOSD-ENROL-{row['uin']}",
            "active",
            OBSERVED_AT,
            uin=row["uin"],
            duplicate_flag=_bool(row["duplicate_flag"]),
        )
        for row in rows["programme_mis_enrollment"]
    ]
    _insert_rows(
        connection,
        "beneficiary_enrolment_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "uin",
            "duplicate_flag",
        ),
        records,
    )


def _publish_sipf(connection: sqlite3.Connection, rows: dict[str, list[dict[str, object]]]) -> None:
    connection.executescript(
        """
        CREATE TABLE pension_case_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            pensioner_uin TEXT NOT NULL UNIQUE,
            payment_status TEXT NOT NULL
        ) STRICT;
        CREATE TABLE survivor_case_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            spouse_uin TEXT NOT NULL UNIQUE,
            survivor_eligible INTEGER NOT NULL CHECK (survivor_eligible IN (0, 1))
        ) STRICT;
        CREATE VIEW relay_pension_payment AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               pensioner_uin, payment_status
        FROM pension_case_source;
        CREATE VIEW relay_survivor_case AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               spouse_uin, survivor_eligible
        FROM survivor_case_source;
        """
    )
    pension_records = []
    survivor_records = []
    for row in rows["pension_case"]:
        pension_records.append(
            _record(
                row["pension_case_id"],
                row["pension_status"],
                row["observed_at"],
                pensioner_uin=row["pensioner_uin"],
                payment_status=row["payment_status"],
            )
        )
        if row["spouse_uin"]:
            survivor_records.append(
                _record(
                    f"{row['pension_case_id']}-SURVIVOR",
                    "active",
                    row["observed_at"],
                    spouse_uin=row["spouse_uin"],
                    survivor_eligible=_bool(row["survivor_eligible"]),
                )
            )
    _insert_rows(
        connection,
        "pension_case_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "pensioner_uin",
            "payment_status",
        ),
        pension_records,
    )
    _insert_rows(
        connection,
        "survivor_case_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "spouse_uin",
            "survivor_eligible",
        ),
        survivor_records,
    )


def _publish_nagdi(connection: sqlite3.Connection, rows: dict[str, list[dict[str, object]]]) -> None:
    connection.executescript(
        """
        CREATE TABLE farmer_voucher_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            farmer_id TEXT NOT NULL UNIQUE,
            farmer_registered INTEGER NOT NULL CHECK (farmer_registered IN (0, 1)),
            data_use_authorized INTEGER NOT NULL CHECK (data_use_authorized IN (0, 1)),
            active_smallholder_farmer INTEGER NOT NULL CHECK (active_smallholder_farmer IN (0, 1)),
            active_farm_parcel INTEGER NOT NULL CHECK (active_farm_parcel IN (0, 1)),
            crop_declared_for_season INTEGER NOT NULL CHECK (crop_declared_for_season IN (0, 1)),
            district_climate_risk_active INTEGER NOT NULL CHECK (district_climate_risk_active IN (0, 1)),
            voucher_entitlement_current INTEGER NOT NULL CHECK (voucher_entitlement_current IN (0, 1)),
            voucher_not_redeemed INTEGER NOT NULL CHECK (voucher_not_redeemed IN (0, 1))
        ) STRICT;
        CREATE TABLE livestock_movement_source (
            record_id TEXT PRIMARY KEY,
            record_revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            herd_id TEXT NOT NULL UNIQUE,
            farmer_id TEXT NOT NULL,
            registered_herd INTEGER NOT NULL CHECK (registered_herd IN (0, 1)),
            herd_vaccination_current INTEGER NOT NULL CHECK (herd_vaccination_current IN (0, 1)),
            origin_district_not_quarantined_for_species INTEGER NOT NULL CHECK (origin_district_not_quarantined_for_species IN (0, 1)),
            destination_district_open INTEGER NOT NULL CHECK (destination_district_open IN (0, 1)),
            no_conflicting_open_movement_permit INTEGER NOT NULL CHECK (no_conflicting_open_movement_permit IN (0, 1))
        ) STRICT;
        CREATE VIEW relay_farmer_voucher AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               farmer_id, farmer_registered, data_use_authorized,
               active_smallholder_farmer, active_farm_parcel,
               crop_declared_for_season, district_climate_risk_active,
               voucher_entitlement_current, voucher_not_redeemed
        FROM farmer_voucher_source;
        CREATE VIEW relay_livestock_movement AS
        SELECT record_id, record_revision, lifecycle_state, recorded_at,
               herd_id, farmer_id, registered_herd,
               herd_vaccination_current,
               origin_district_not_quarantined_for_species,
               destination_district_open,
               no_conflicting_open_movement_permit
        FROM livestock_movement_source;
        """
    )
    voucher_records = [
        _record(
            f"NAGDI-VOUCHER-{row['farmer_id']}",
            "active",
            OBSERVED_AT,
            farmer_id=row["farmer_id"],
            farmer_registered=_bool(row["farmer_registered"]),
            data_use_authorized=_bool(row["data_use_authorized"]),
            active_smallholder_farmer=_bool(row["active_smallholder_farmer"]),
            active_farm_parcel=_bool(row["active_farm_parcel"]),
            crop_declared_for_season=_bool(row["crop_declared_for_season"]),
            district_climate_risk_active=_bool(row["district_climate_risk_active"]),
            voucher_entitlement_current=_bool(row["voucher_entitlement_current"]),
            voucher_not_redeemed=_bool(row["voucher_not_redeemed"]),
        )
        for row in rows["farmer_voucher"]
    ]
    movement_records = [
        _record(
            f"NAGDI-MOVEMENT-{row['herd_id']}",
            "active",
            OBSERVED_AT,
            herd_id=row["herd_id"],
            farmer_id=row["farmer_id"],
            registered_herd=_bool(row["registered_herd"]),
            herd_vaccination_current=_bool(row["herd_vaccination_current"]),
            origin_district_not_quarantined_for_species=_bool(
                row["origin_district_not_quarantined_for_species"]
            ),
            destination_district_open=_bool(row["destination_district_open"]),
            no_conflicting_open_movement_permit=_bool(
                row["no_conflicting_open_movement_permit"]
            ),
        )
        for row in rows["livestock_movement"]
    ]
    _insert_rows(
        connection,
        "farmer_voucher_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "farmer_id",
            "farmer_registered",
            "data_use_authorized",
            "active_smallholder_farmer",
            "active_farm_parcel",
            "crop_declared_for_season",
            "district_climate_risk_active",
            "voucher_entitlement_current",
            "voucher_not_redeemed",
        ),
        voucher_records,
    )
    _insert_rows(
        connection,
        "livestock_movement_source",
        (
            "record_id",
            "record_revision",
            "lifecycle_state",
            "recorded_at",
            "herd_id",
            "farmer_id",
            "registered_herd",
            "herd_vaccination_current",
            "origin_district_not_quarantined_for_species",
            "destination_district_open",
            "no_conflicting_open_movement_permit",
        ),
        movement_records,
    )


_RELAY_PUBLISHERS: dict[
    str, Callable[[sqlite3.Connection, dict[str, list[dict[str, object]]]], None]
] = {
    "cra": _publish_cra,
    "nia": _publish_nia,
    "mosd": _publish_mosd,
    "sipf": _publish_sipf,
    "nagdi": _publish_nagdi,
}


def publish_relay_sources(root: Path) -> dict[str, Path]:
    root = root.resolve()
    rows = _publisher_rows(root)
    published = {}
    for authority, filename in RELAY_FILENAMES.items():
        target = root / RELAY_DIRECTORY / filename
        populate = _RELAY_PUBLISHERS[authority]
        _replace_database(target, lambda connection, p=populate: p(connection, rows))
        published[authority] = target
    return published


def _extract_rows(
    authority: str, rows: dict[str, list[dict[str, object]]]
) -> tuple[str, tuple[str, ...], list[tuple[object, ...]]]:
    if authority == "cra":
        people = {row["uin"]: row for row in rows["civil_person"]}
        records = []
        for row in rows["civil_person_projection"]:
            person = people[row["uin"]]
            records.append(
                _record(
                    person["person_id"],
                    "registered" if row["birth_brn"] else "unregistered",
                    person["observed_at"],
                    uin=row["uin"],
                    birth_date=row["birth_date"],
                    birth_brn=row["birth_brn"] or None,
                )
            )
        return (
            "birth_evidence",
            (
                "record_id",
                "record_revision",
                "lifecycle_state",
                "recorded_at",
                "uin",
                "birth_date",
                "birth_brn",
            ),
            records,
        )
    if authority == "nia":
        records = [
            _record(
                row["person_id"],
                row["identity_status"],
                row["updated_at"],
                uin=row["uin"],
                identity_status=row["identity_status"],
                alive=_bool(row["alive"]),
            )
            for row in rows["population_person"]
        ]
        return (
            "population_evidence",
            (
                "record_id",
                "record_revision",
                "lifecycle_state",
                "recorded_at",
                "uin",
                "identity_status",
                "alive",
            ),
            records,
        )
    if authority == "sro":
        records = [
            _record(
                f"SRO-POVERTY-{row['uin']}",
                "current",
                OBSERVED_AT,
                uin=row["uin"],
                poverty_band=row["poverty_band"],
            )
            for row in rows["child_benefit_household"]
        ]
        return (
            "poverty_evidence",
            (
                "record_id",
                "record_revision",
                "lifecycle_state",
                "recorded_at",
                "uin",
                "poverty_band",
            ),
            records,
        )
    raise ValueError("authority must be one of: cra, nia, sro")


def _create_extract_table(
    connection: sqlite3.Connection, table: str, columns: Sequence[str]
) -> None:
    types = {
        "alive": "INTEGER NOT NULL CHECK (alive IN (0, 1))",
    }
    nullable = {"birth_brn"}
    definitions = []
    for column in columns:
        if column == "record_id":
            definition = "TEXT PRIMARY KEY"
        elif column in types:
            definition = types[column]
        elif column in nullable:
            definition = "TEXT"
        else:
            definition = "TEXT NOT NULL"
        definitions.append(f"{column} {definition}")
    connection.execute(f"CREATE TABLE {table} ({', '.join(definitions)}) STRICT")


def _validate_extract_id(extract_id: str) -> None:
    if not _EXTRACT_ID.fullmatch(extract_id):
        raise ValueError("extract_id must be a filename-safe identifier")


def _validate_published_at(published_at: str) -> None:
    if not _RFC3339.fullmatch(published_at):
        raise ValueError("published_at must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(published_at)
    except ValueError:
        raise ValueError("published_at must be an RFC 3339 timestamp") from None
    if parsed.utcoffset() is None:
        raise ValueError("published_at must be an RFC 3339 timestamp")


def _published_datetime(published_at: str) -> datetime:
    _validate_published_at(published_at)
    return datetime.fromisoformat(published_at).astimezone(UTC)


def canonical_published_at(published_at: str) -> str:
    """Return one stable UTC representation for an explicit publication time."""

    parsed = _published_datetime(published_at)
    timespec = "microseconds" if parsed.microsecond else "seconds"
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")


def timestamped_extract_id(authority: str, published_at: str) -> str:
    """Derive a deterministic immutable extract identifier from its authority and time."""

    if authority not in EXTRACT_PREFIXES:
        raise ValueError("authority must be one of: cra, nia, sro")
    parsed = _published_datetime(published_at)
    timestamp = parsed.strftime("%Y%m%dT%H%M%S")
    if parsed.microsecond:
        timestamp += f"{parsed.microsecond:06d}"
    return f"{EXTRACT_PREFIXES[authority]}-{timestamp}Z"


def _database_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro&immutable=1"


def validate_extract(
    path: Path,
    authority: str,
    *,
    observed_at: str,
    expected_extract_id: str | None = None,
    expected_published_at: str | None = None,
    maximum_age_seconds: int = MAX_EXTRACT_AGE_SECONDS,
) -> ExtractMetadata:
    """Validate the immutable file, exact metadata, schema, and freshness."""

    if authority not in PUBLISHERS:
        raise ValueError("authority must be one of: cra, nia, sro")
    if maximum_age_seconds < 0:
        raise ValueError("maximum_age_seconds must not be negative")
    observed = _published_datetime(observed_at)
    path = path.absolute()
    if path.is_symlink() or not path.is_file():
        raise ExtractValidationError("extract is not an immutable regular file")
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        raise ExtractValidationError("extract has a writable mode")
    if path.suffix != ".sqlite":
        raise ExtractValidationError("extract filename does not match its binding")
    bound_extract_id = path.stem
    try:
        _validate_extract_id(bound_extract_id)
    except ValueError:
        raise ExtractValidationError(
            "extract filename does not match its binding"
        ) from None
    if expected_extract_id is not None and bound_extract_id != expected_extract_id:
        raise ExtractValidationError("extract filename does not match its binding")

    try:
        with sqlite3.connect(_database_uri(path), uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ExtractValidationError("extract integrity check failed")
            metadata_columns = tuple(
                row[1]
                for row in connection.execute("PRAGMA table_info(evidence_extract)")
            )
            if metadata_columns != ("published_at", "publisher", "extract_id"):
                raise ExtractValidationError("extract metadata schema is invalid")
            metadata_rows = connection.execute(
                "SELECT published_at, publisher, extract_id FROM evidence_extract"
            ).fetchall()
            if len(metadata_rows) != 1:
                raise ExtractValidationError("extract metadata cardinality is invalid")
            published_at, publisher, extract_id = metadata_rows[0]
            table, expected_columns = EXTRACT_TABLES[authority]
            actual_columns = tuple(
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual_columns != expected_columns:
                raise ExtractValidationError("extract source schema is invalid")
    except ExtractValidationError:
        raise
    except (OSError, sqlite3.Error):
        raise ExtractValidationError("extract cannot be validated") from None

    if (
        not isinstance(published_at, str)
        or not isinstance(publisher, str)
        or not isinstance(extract_id, str)
    ):
        raise ExtractValidationError("extract metadata types are invalid")
    if publisher != PUBLISHERS[authority] or extract_id != bound_extract_id:
        raise ExtractValidationError("extract metadata does not match its binding")
    try:
        published = _published_datetime(published_at)
    except ValueError:
        raise ExtractValidationError("extract publication time is invalid") from None
    if expected_published_at is not None:
        try:
            expected_published = canonical_published_at(expected_published_at)
        except ValueError:
            raise ValueError("expected_published_at must be an RFC 3339 timestamp") from None
        if canonical_published_at(published_at) != expected_published:
            raise ExtractValidationError("extract metadata does not match its binding")
    age = observed - published
    if age < timedelta(0):
        raise ExtractValidationError("extract publication time is in the future")
    if age > timedelta(seconds=maximum_age_seconds):
        raise StaleExtractError("extract is outside its accepted age")
    return ExtractMetadata(published_at, publisher, extract_id)


def extract_path(root: Path, extract_id: str) -> Path:
    _validate_extract_id(extract_id)
    return root.resolve() / EVIDENCE_DIRECTORY / f"{extract_id}.sqlite"


def publish_extract(
    root: Path, authority: str, published_at: str, extract_id: str
) -> Path:
    if authority not in PUBLISHERS:
        raise ValueError("authority must be one of: cra, nia, sro")
    _validate_published_at(published_at)
    target = extract_path(root, extract_id)
    rows = _publisher_rows(root.resolve())
    table, columns, records = _extract_rows(authority, rows)

    def populate(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE evidence_extract (
                published_at TEXT NOT NULL,
                publisher TEXT NOT NULL,
                extract_id TEXT NOT NULL
            ) STRICT
            """
        )
        connection.execute(
            "INSERT INTO evidence_extract VALUES (?, ?, ?)",
            (published_at, PUBLISHERS[authority], extract_id),
        )
        _create_extract_table(connection, table, columns)
        _insert_rows(connection, table, columns, records)

    _create_immutable_database(target, populate)
    return target


def publish_all(root: Path) -> dict[str, Path]:
    root = root.resolve()
    extract_targets = {
        authority: extract_path(root, extract_id)
        for authority, extract_id in DEFAULT_EXTRACTS.items()
    }
    existing = [path for path in extract_targets.values() if path.exists()]
    if existing:
        raise FileExistsError("an immutable Evidence extract target already exists")
    published = publish_relay_sources(root)
    for authority, extract_id in DEFAULT_EXTRACTS.items():
        published[f"{authority}_extract"] = publish_extract(
            root, authority, OBSERVED_AT, extract_id
        )
    return published


def mutate_mosd_state(
    database: Path, uin: str, duplicate_flag: bool, recorded_at: str
) -> None:
    database = database.resolve()
    before = database.stat()
    with sqlite3.connect(database) as connection:
        _configure(connection)
        current = connection.execute(
            "SELECT record_id, lifecycle_state FROM beneficiary_enrolment_source WHERE uin = ?",
            (uin,),
        ).fetchone()
        if current is None:
            raise LookupError("MoSD enrolment record was not found")
        revision_input: dict[str, Any] = {
            "record_id": current[0],
            "lifecycle_state": current[1],
            "recorded_at": recorded_at,
            "uin": uin,
            "duplicate_flag": int(duplicate_flag),
        }
        connection.execute(
            """
            UPDATE beneficiary_enrolment_source
            SET duplicate_flag = ?, record_revision = ?, recorded_at = ?
            WHERE uin = ?
            """,
            (int(duplicate_flag), _revision(revision_input), recorded_at, uin),
        )
        connection.commit()
    after = database.stat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise RuntimeError("MoSD publication replaced the live database path")
    _ensure_no_sidecars(database)


def _parse_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Solmara SQLite sources")
    commands = parser.add_subparsers(dest="command", required=True)
    default_root = Path(__file__).resolve().parents[2]

    publish_all_command = commands.add_parser("publish-all")
    publish_all_command.add_argument("--root", type=Path, default=default_root)

    extract = commands.add_parser("publish-extract")
    extract.add_argument("--root", type=Path, default=default_root)
    extract.add_argument("--authority", choices=sorted(PUBLISHERS), required=True)
    extract.add_argument("--published-at", required=True)
    extract.add_argument("--extract-id", required=True)

    mutation = commands.add_parser("mutate-mosd")
    mutation.add_argument("--root", type=Path, default=default_root)
    mutation.add_argument("--database", type=Path)
    mutation.add_argument("--uin", required=True)
    mutation.add_argument("--duplicate-flag", type=_parse_bool, required=True)
    mutation.add_argument("--recorded-at", required=True)

    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "publish-all":
        publish_all(root)
    elif args.command == "publish-extract":
        publish_extract(root, args.authority, args.published_at, args.extract_id)
    else:
        database = args.database or root / RELAY_DIRECTORY / RELAY_FILENAMES["mosd"]
        mutate_mosd_state(database, args.uin, args.duplicate_flag, args.recorded_at)


if __name__ == "__main__":
    main()
