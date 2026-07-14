from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

OBSERVED_AT = "2026-07-04T09:00:00Z"
SOURCE_DATE = date(2026, 7, 4)
PURPOSE_CHILD = "https://id.registrystack.org/solmara/purpose/child-benefit-review"
PURPOSE_ALL = "all"


@dataclass(frozen=True)
class Persona:
    key: str
    roster_primary_id: str
    legacy_nid: str
    given_name: str
    family_name: str
    sex: str
    birth_date: str
    district_code: str
    settlement_type: str
    role: str
    farmer_alias: str = ""


PERSONAS = [
    Persona("child_positive", "2300010248", "NID-1001", "Mateo", "Santos", "male", "2022-03-14", "XS-0101", "rural", "child benefit positive child"),
    Persona("mother_positive", "2300018263", "NID-1002", "Elena", "Dela Cruz", "female", "1992-11-02", "XS-0101", "rural", "Mateo guardian"),
    Persona("child_positive_head", "2300027390", "NID-1003", "Luis", "Okafor", "male", "1989-08-20", "XS-0101", "rural", "household head for child benefit positive path"),
    Persona("above_threshold_child", "2300036523", "NID-1004", "Hana", "Aquino", "female", "2021-01-29", "XS-0301", "urban", "child benefit denied above threshold"),
    Persona("above_threshold_guardian", "2300045650", "NID-1005", "Priya", "Mensah", "female", "1985-07-08", "XS-0301", "urban", "guardian for above-threshold child household"),
    Persona("duplicate_enrolled_child", "2300054788", "NID-1006", "Tomas", "Bello", "male", "2020-06-17", "XS-0302", "urban", "child benefit denied duplicate enrollment"),
    Persona("duplicate_enrolled_guardian", "2300063915", "NID-1007", "Joana", "Bello", "female", "1985-09-10", "XS-0302", "urban", "guardian for duplicate-enrollment control"),
    Persona("unregistered_child", "2300073046", "NID-1008", "Karim", "Kone", "male", "2020-05-18", "XS-0202", "rural", "birth registration gap"),
    Persona("guardian", "2300082172", "NID-1009", "Aisha", "Kone", "female", "1981-04-23", "XS-0202", "rural", "guardian for unregistered-birth inclusion path"),
    Persona("deceased_child_control", "2300091305", "NID-1010", "Esteban", "Cruz", "male", "2019-12-12", "XS-0203", "rural", "deceased child-benefit control"),
    Persona("deceased_child_guardian", "2300100431", "NID-1011", "Miriam", "Cruz", "female", "1988-12-12", "XS-0203", "rural", "guardian for deceased control path"),
    Persona("deceased_pensioner", "2300109568", "NID-2001", "Rafael", "Nkomo", "male", "1944-02-01", "XS-0301", "urban", "pension positive deceased member"),
    Persona("survivor_spouse", "2300118698", "NID-2002", "Imani", "Nkomo", "female", "1950-10-03", "XS-0301", "urban", "survivor benefit positive spouse"),
    Persona("deceased_lag", "2300127827", "NID-2004", "Otto", "Ferreira", "male", "1947-05-05", "XS-0302", "urban", "pension stale-data failure death not registered"),
    Persona("survivor_waits", "2300136959", "NID-2005", "Lucia", "Ferreira", "female", "1951-06-30", "XS-0302", "urban", "survivor claim waits for death reconciliation"),
    Persona("divorced_head", "2300146081", "NID-2006", "Mina", "Rahman", "female", "1980-03-19", "XS-0303", "urban", "survivor denied marriage dissolved"),
    Persona("former_spouse", "2300155218", "NID-2010", "Pavel", "Rahman", "male", "1979-01-11", "XS-0303", "urban", "deceased former spouse for dissolved-marriage control"),
    Persona("farmer_positive", "FR-1001", "NID-2011", "Amina", "Kone", "female", "1988-02-22", "XS-0103", "rural", "farmer voucher positive and livestock movement positive owner", "FR-1001"),
    Persona("farmer_missing_auth", "FR-1002", "NID-2012", "Diego", "Santos", "male", "1976-04-04", "XS-0102", "rural", "farmer voucher denied missing data-use authorization", "FR-1002"),
    Persona("farmer_risk_denied", "FR-1003", "NID-2013", "Noor", "Patel", "female", "1990-09-09", "XS-0402", "rural", "farmer voucher denied outside eligible climate-risk band", "FR-1003"),
    Persona("livestock_quarantine", "FR-1004", "NID-2014", "Beatriz", "Okafor", "female", "1982-10-10", "XS-0401", "rural", "livestock movement denied species-specific quarantine", "FR-1004"),
    Persona("livestock_vaccination", "FR-1005", "NID-2015", "Sefu", "Dela Cruz", "male", "1984-12-01", "XS-0403", "rural", "livestock movement denied incomplete vaccination evidence", "FR-1005"),
]

PROVINCES = [
    ("XS-01", "Anvela", None),
    ("XS-02", "Tolara", None),
    ("XS-03", "Mendira", None),
    ("XS-04", "Corvala", None),
]
DISTRICTS = [
    ("XS-0101", "Ketterin", "XS-01"),
    ("XS-0102", "Ovasse", "XS-01"),
    ("XS-0103", "Brenholm", "XS-01"),
    ("XS-0201", "Salvet", "XS-02"),
    ("XS-0202", "Marindi", "XS-02"),
    ("XS-0203", "Velcor", "XS-02"),
    ("XS-0301", "Lydessa", "XS-03"),
    ("XS-0302", "Orivale", "XS-03"),
    ("XS-0303", "Carrowen", "XS-03"),
    ("XS-0401", "Eastmere", "XS-04"),
    ("XS-0402", "Navaro", "XS-04"),
    ("XS-0403", "Vestrel", "XS-04"),
]

TABLES = {
    "ministries/interior-civil/fixtures": [
        "civil_person", "birth_event", "death_event", "marriage_event",
        "marriage_termination_event", "civil_status_record", "certificate",
        "relationship", "civil_identifier", "civil_person_projection",
    ],
    "ministries/interior-population/fixtures": [
        "population_person", "identity_document", "consent_directive",
        "schema.sql", "load.sql", "001-schema.sql", "002-load.sql",
    ],
    "ministries/social-development/fixtures": [
        "household", "household_member", "socio_economic_profile",
        "scoring_event", "program", "eligibility_decision", "enrollment",
        "entitlement", "payment_event", "grievance", "social_registry_household",
        "child_benefit_household", "programme_mis_enrollment",
    ],
    "ministries/labour-pensions/fixtures": [
        "sipf_contribution_account", "sipf_contribution_period",
        "sipf_pension_award", "sipf_payment_instruction",
        "sipf_proof_of_life_check", "sipf_survivor_link", "pension_case",
    ],
    "ministries/agriculture-nagdi/fixtures": [
        "Farmers", "FarmerIdentifiers", "FarmerGroups",
        "DataUseAuthorizations", "ChangeLog", "Holdings", "Parcels",
        "CropDeclarations", "TenureClaims", "Programs",
        "VoucherEntitlements", "VoucherRedemptions", "ExtensionVisits",
        "Suppliers", "ProgramRules", "InputPackages", "BudgetAllocations",
        "RedemptionReconciliation", "Grievances", "Sanctions",
        "DistrictClimateRisk", "RainfallObservations", "MarketPrices",
        "CropCalendar", "AdvisoryRules", "VoucherMarketSizingCells",
        "LivestockHoldings", "Premises", "Herds", "Animals",
        "Vaccinations", "QuarantineZones", "MovementApplications",
        "MovementPermits", "MovementEvents", "PurposePolicies",
        "SourceSubmissions", "ValidationIssues", "DuplicateCandidates",
        "CorrectionRequests", "VoucherEligibilitySnapshots",
        "LivestockMovementSnapshots", "MarketSizingCells", "farmer_voucher",
        "livestock_movement",
    ],
}


def verhoeff_digit(num: str) -> str:
    d = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    p = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, item in enumerate(reversed(num)):
        c = d[c][p[(i + 1) % 8][int(item)]]
    return str(inv[c])


def valid_uin(uin: str) -> bool:
    if len(uin) != 10 or not uin.isdigit() or uin[0] in "01":
        return False
    if "786" in uin or "666" in uin:
        return False
    if any(str(n) * 4 in uin for n in range(10)):
        return False
    return verhoeff_digit(uin[:-1]) == uin[-1]


def make_uin(seed: int) -> str:
    candidate = seed
    while True:
        stem = f"{candidate:09d}"
        if stem[0] not in "01" and "786" not in stem and "666" not in stem and not any(str(n) * 4 in stem for n in range(10)):
            uin = stem + verhoeff_digit(stem)
            if valid_uin(uin):
                return uin
        candidate += 37


def add_meta(row: dict[str, object], source: str) -> dict[str, object]:
    result = {k: ("" if v is None else v) for k, v in row.items()}
    result["observed_at"] = OBSERVED_AT
    result["source_system"] = source
    return result


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def rectangle(x1: float, y1: float, x2: float, y2: float) -> list[list[float]]:
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]


def feature(code: str, name: str, level: str, parent: str | None, coords: list[list[float]]) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "admin_code": code,
            "admin_name": name,
            "admin_level": level,
            "parent_admin_code": parent,
            "crs": "EPSG:4326",
            "valid_from": "2026-01-01",
            "valid_until": "",
        },
        "geometry": {"type": "Polygon", "coordinates": [coords]},
    }


def geo_features() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    country = [feature("XS", "Republic of Solmara", "country", None, rectangle(79.0, -11.0, 80.2, -9.8))]
    province_boxes = {
        "XS-01": (79.0, -10.4, 79.6, -9.8),
        "XS-02": (79.0, -11.0, 79.6, -10.4),
        "XS-03": (79.6, -11.0, 80.2, -10.4),
        "XS-04": (79.6, -10.4, 80.2, -9.8),
    }
    provinces = [feature(code, name, "province", None, rectangle(*province_boxes[code])) for code, name, _ in PROVINCES]
    districts = []
    for pcode, box in province_boxes.items():
        x1, y1, x2, y2 = box
        width = (x2 - x1) / 3
        for offset, (dcode, dname, parent) in enumerate([d for d in DISTRICTS if d[2] == pcode]):
            dx1 = x1 + offset * width
            dx2 = x1 + (offset + 1) * width
            districts.append(feature(dcode, dname, "district", parent, rectangle(dx1, y1, dx2, y2)))
    districts.append(feature("XS-0203-OLD", "Velcor old boundary", "district_version", "XS-02", rectangle(79.35, -11.0, 79.6, -10.4)))
    return country, provinces, districts


def build_people() -> tuple[list[dict[str, object]], dict[str, str], dict[str, Persona | None]]:
    rng = random.Random(204)
    given = ["Ari", "Mika", "Nela", "Tomas", "Lina", "Zaid", "Rina", "Kiran", "Eli", "Mara", "Tala", "Rafi"]
    family = ["Santos", "Okafor", "Dela Cruz", "Aquino", "Kone", "Mensah", "Raman", "Almeida", "Mori", "Khan"]
    people = []
    uins: dict[str, str] = {}
    persona_by_uin: dict[str, Persona | None] = {}
    for idx, persona in enumerate(PERSONAS, start=1):
        uin = make_uin(230000000 + idx * 913)
        uins[persona.key] = uin
        status = "active"
        if persona.key in {"deceased_pensioner", "former_spouse", "deceased_child_control"}:
            status = "deceased"
        alive = persona.key not in {"deceased_pensioner", "former_spouse", "deceased_child_control"}
        pending = ""
        people.append({
            "uin": uin,
            "person_id": f"CP-{idx:06d}",
            "legacy_nid": persona.legacy_nid,
            "given_name": persona.given_name,
            "family_name": persona.family_name,
            "birth_date": persona.birth_date,
            "sex": persona.sex,
            "district_code": persona.district_code,
            "address_area": f"{persona.district_code} civic area",
            "settlement_type": persona.settlement_type,
            "identity_status": status,
            "pending_merge_with_uin": pending,
            "match_basis": "",
            "alive": str(alive).lower(),
            "birth_brn": "" if persona.key == "unregistered_child" else f"BRN-{persona.birth_date[:4]}-{persona.district_code[3:]}-{idx:05d}",
            "updated_at": "2026-07-01T08:00:00Z" if persona.key == "deceased_lag" else OBSERVED_AT,
        })
        persona_by_uin[uin] = persona
    for n in range(len(PERSONAS) + 1, 1001):
        year = rng.choices(range(1940, 2026), weights=[1 if y < 1955 else 3 if y < 1990 else 5 for y in range(1940, 2026)], k=1)[0]
        born = date(year, rng.randint(1, 12), rng.randint(1, 28))
        district = DISTRICTS[(n - 1) % len(DISTRICTS)][0]
        rural = district[:5] in {"XS-01", "XS-02", "XS-04"}
        uin = make_uin(231000000 + n * 913)
        people.append({
            "uin": uin,
            "person_id": f"CP-{n:06d}",
            "legacy_nid": "",
            "given_name": f"{given[n % len(given)]}{n}",
            "family_name": family[n % len(family)],
            "birth_date": born.isoformat(),
            "sex": "female" if n % 2 else "male",
            "district_code": district,
            "address_area": f"{district} sector {1 + n % 9}",
            "settlement_type": "rural" if rural and n % 5 else "urban",
            "identity_status": "active",
            "pending_merge_with_uin": "",
            "match_basis": "",
            "alive": "true",
            "birth_brn": "" if year >= 2021 and n % 5 == 0 else f"BRN-{year}-{district[3:]}-{n:05d}",
            "updated_at": OBSERVED_AT,
        })
        persona_by_uin[uin] = None
    return people, uins, persona_by_uin


def build_rows(root: Path) -> dict[str, list[dict[str, object]]]:
    people, uins, persona_by_uin = build_people()
    by_uin = {p["uin"]: p for p in people}
    persona_manifest = []
    for persona in PERSONAS:
        person = by_uin[uins[persona.key]]
        persona_manifest.append(add_meta({
            "persona_id": persona.key,
            "uin": person["uin"],
            "roster_primary_id": persona.roster_primary_id,
            "civil_person_id": person["person_id"],
            "legacy_nid": persona.legacy_nid,
            "legacy_farmer_id": persona.farmer_alias,
            "given_name": persona.given_name,
            "family_name": persona.family_name,
            "role": persona.role,
            "district_code": persona.district_code,
        }, "SOLMARA-GENERATOR"))
    civil_people = []
    births = []
    deaths = []
    statuses = []
    certificates = []
    identifiers = []
    relationships = []
    for i, person in enumerate(people, start=1):
        persona = persona_by_uin[person["uin"]]
        life_status = "deceased" if persona and persona.key == "deceased_pensioner" else "alive"
        death_date = "2026-03-03" if persona and persona.key == "deceased_pensioner" else ""
        civil_people.append(add_meta({
            "person_id": person["person_id"], "uin": person["uin"], "given_name": person["given_name"],
            "family_name": person["family_name"], "sex": person["sex"], "birth_date": person["birth_date"],
            "birth_place_district_code": person["district_code"], "life_status": life_status, "death_date": death_date,
        }, "CRA-CORE"))
        if person["birth_brn"]:
            event_id = f"BE-{i:05d}"
            brn = person["birth_brn"]
            births.append(add_meta({
                "event_id": event_id, "brn": brn, "child_person_id": person["person_id"],
                "mother_person_id": by_uin[uins["mother_positive"]]["person_id"] if i == 1 else "",
                "father_person_id": "", "informant_person_id": person["person_id"],
                "informant_relationship": "guardian" if persona and persona.key == "unregistered_child" else "parent",
                "date_of_birth": person["birth_date"], "place_type": "home", "facility_id": "",
                "birth_attendant": "traditional_birth_attendant", "sex_at_birth": person["sex"],
            }, "CRA-CORE"))
            statuses.append(add_meta({
                "record_id": f"CSR-{i:05d}", "record_type": "birth", "registration_number": brn,
                "person_id": person["person_id"], "event_id": event_id, "registration_status": "registered",
                "registration_date": (date.fromisoformat(person["birth_date"]) + timedelta(days=20)).isoformat(),
            }, "CRA-CORE"))
            certificates.append(add_meta({
                "certificate_number": f"XS-CRA-CERT-{i:06d}", "record_id": f"CSR-{i:05d}",
                "certificate_type": "birth_certificate", "issue_date": "2026-01-10",
                "issuing_office": "CRA district office", "valid_until": "",
            }, "CRA-CORE"))
            identifiers.append(add_meta({
                "identifier_id": f"CI-{i:06d}", "person_id": person["person_id"], "scheme": "brn",
                "value": brn, "status": "active", "issued_on": "2026-01-10",
            }, "CRA-CORE"))
        identifiers.append(add_meta({
            "identifier_id": f"CI-{100000 + i:06d}", "person_id": person["person_id"], "scheme": "uin",
            "value": person["uin"], "status": "active", "issued_on": "2026-01-10",
        }, "CRA-CORE"))
        if person["legacy_nid"]:
            identifiers.append(add_meta({
                "identifier_id": f"CI-{200000 + i:06d}", "person_id": person["person_id"], "scheme": "legacy_nid",
                "value": person["legacy_nid"], "status": "active", "issued_on": "2026-01-10",
            }, "CRA-CORE"))
    for key, drn, death_date, civil_life in [
        ("deceased_child_control", "DRN-2026-0203-00001", "2026-02-14", "deceased"),
        ("deceased_pensioner", "DRN-2026-0301-00002", "2026-03-03", "deceased"),
        ("former_spouse", "DRN-2026-0303-00003", "2026-04-09", "deceased"),
    ]:
        person = by_uin[uins[key]]
        deaths.append(add_meta({
            "event_id": f"DE-{len(deaths)+1:05d}", "drn": drn, "deceased_person_id": person["person_id"],
            "date_of_death": death_date, "place_type": "home", "facility_id": "",
            "cause_of_death": "natural causes", "manner_of_death": "natural",
            "medical_certifier_present": "true", "informant_person_id": by_uin[uins["survivor_spouse"]]["person_id"],
            "informant_relationship": "spouse",
        }, "CRA-CORE"))
        statuses.append(add_meta({
            "record_id": f"CSR-{1001 + len(deaths):05d}", "record_type": "death", "registration_number": drn,
            "person_id": person["person_id"], "event_id": f"DE-{len(deaths):05d}",
            "registration_status": "registered", "registration_date": death_date,
        }, "CRA-CORE"))
        if civil_life == "deceased":
            for row in civil_people:
                if row["person_id"] == person["person_id"]:
                    row["life_status"] = "deceased"
                    row["death_date"] = death_date
    marriages = [
        add_meta({"event_id": "ME-00001", "mrn": "MRN-1970-0401-00001", "spouse_1_person_id": by_uin[uins["deceased_pensioner"]]["person_id"], "spouse_2_person_id": by_uin[uins["survivor_spouse"]]["person_id"], "marriage_date": "1970-05-12", "district_code": "XS-0401", "marriage_type": "civil"}, "CRA-CORE"),
        add_meta({"event_id": "ME-00002", "mrn": "MRN-2010-0302-00002", "spouse_1_person_id": by_uin[uins["divorced_head"]]["person_id"], "spouse_2_person_id": by_uin[uins["former_spouse"]]["person_id"], "marriage_date": "2010-09-18", "district_code": "XS-0302", "marriage_type": "civil"}, "CRA-CORE"),
    ]
    terminations = [add_meta({"event_id": "MT-00001", "mrn": "MRN-2010-0302-00002", "termination_type": "divorce", "effective_date": "2025-11-30", "court_reference": "XS-FC-2025-7781"}, "CRA-CORE")]
    relationships.extend([
        add_meta({"relationship_id": "REL-000001", "subject_person_id": by_uin[uins["deceased_pensioner"]]["person_id"], "related_person_id": by_uin[uins["survivor_spouse"]]["person_id"], "relationship_type": "spouse", "source_record_id": "CSR-02001", "effective_from": "1970-05-12", "effective_until": "2026-03-03", "relationship_status": "dissolved"}, "CRA-CORE"),
        add_meta({"relationship_id": "REL-000002", "subject_person_id": by_uin[uins["divorced_head"]]["person_id"], "related_person_id": by_uin[uins["former_spouse"]]["person_id"], "relationship_type": "spouse", "source_record_id": "CSR-02002", "effective_from": "2010-09-18", "effective_until": "2025-11-30", "relationship_status": "dissolved"}, "CRA-CORE"),
    ])
    docs = [add_meta({"document_id": f"DOC-{i:06d}", "uin": p["uin"], "document_type": "national_id_card", "issue_date": "2024-01-01", "expiry_date": "2034-01-01", "document_status": "valid" if p["identity_status"] != "suspended" else "suspended"}, "NIA-SOLMARAID") for i, p in enumerate(people, 1)]
    consents = [
        add_meta({"directive_id": "CONS-000001", "uin": uins["survivor_waits"], "purpose_scope": PURPOSE_ALL, "consent_status": "withdrawn", "expression": "opt_out", "effective_from": "2026-06-01", "effective_until": ""}, "NIA-SOLMARAID"),
        add_meta({"directive_id": "CONS-000002", "uin": uins["mother_positive"], "purpose_scope": PURPOSE_CHILD, "consent_status": "granted", "expression": "opt_in", "effective_from": "2026-01-01", "effective_until": ""}, "NIA-SOLMARAID"),
    ]
    households = []
    members = []
    profiles = []
    scores = []
    household_ids: dict[str, str] = {}
    h = 1
    persona_households = [
        ("HH-002317", "child_positive_head", ["child_positive_head", "mother_positive", "child_positive"], "priority", 34.5),
        ("HH-002318", "guardian", ["guardian", "unregistered_child"], "priority", 28.0),
        ("HH-002319", "above_threshold_guardian", ["above_threshold_guardian", "above_threshold_child"], "not_eligible", 61.0),
        ("HH-002320", "duplicate_enrolled_guardian", ["duplicate_enrolled_guardian", "duplicate_enrolled_child"], "priority", 39.9),
        ("HH-002321", "deceased_child_guardian", ["deceased_child_guardian", "deceased_child_control"], "priority", 31.0),
        ("HH-002322", "divorced_head", ["divorced_head"], "standard", 48.0),
    ]
    for hh_id, head_key, member_keys, band, score in persona_households:
        head = by_uin[uins[head_key]]
        household_ids[head_key] = hh_id
        households.append(add_meta({"household_id": hh_id, "head_uin": head["uin"], "district_code": head["district_code"], "village_name": f"{head['district_code']} village", "address_area": head["address_area"], "household_status": "active", "household_size": len(member_keys), "active_members": len(member_keys), "registration_date": "2025-01-15", "last_reassessment_date": "2026-06-01"}, "SRO-CORE"))
        for key in member_keys:
            members.append(add_meta({"membership_id": f"HM-{len(members)+1:06d}", "household_id": hh_id, "uin": uins[key], "relationship_to_head": "head" if key == head_key else "member", "membership_status": "active", "start_date": "2025-01-15", "end_date": ""}, "SRO-CORE"))
        profiles.append(add_meta({"profile_id": f"SEP-{h:05d}", "household_id": hh_id, "observation_date": "2026-06-01", "instrument": "PMT-SOL-2026", "dwelling_type": "semi_permanent", "water_source": "protected_well", "sanitation_facility": "improved_latrine", "cooking_fuel": "charcoal", "electricity_access": "true", "income_source": "informal_work", "collected_by": "SRO enumerator", "profile_status": "current"}, "SRO-CORE"))
        scores.append(add_meta({"scoring_id": f"SCOR-{h:05d}", "profile_id": f"SEP-{h:05d}", "scoring_rule": "PMT-SOL", "rule_version": "2026.1", "poverty_score": f"{score:.2f}", "score_band": band, "valid_from": "2026-06-01", "valid_until": "2027-06-01", "scoring_status": "current"}, "SRO-CORE"))
        h += 1
    remaining = [p for p in people if p["uin"] not in {m["uin"] for m in members}]
    for chunk in range(274):
        hh_id = f"HH-{3000 + chunk:06d}"
        group = remaining[chunk * 3:(chunk + 1) * 3] or remaining[:1]
        head = group[0]
        households.append(add_meta({"household_id": hh_id, "head_uin": head["uin"], "district_code": head["district_code"], "village_name": f"{head['district_code']} village", "address_area": head["address_area"], "household_status": "active", "household_size": len(group), "active_members": len(group), "registration_date": "2025-03-01", "last_reassessment_date": "2026-05-01"}, "SRO-CORE"))
        for member in group:
            members.append(add_meta({"membership_id": f"HM-{len(members)+1:06d}", "household_id": hh_id, "uin": member["uin"], "relationship_to_head": "head" if member == head else "member", "membership_status": "active", "start_date": "2025-03-01", "end_date": ""}, "SRO-CORE"))
        profiles.append(add_meta({"profile_id": f"SEP-{h:05d}", "household_id": hh_id, "observation_date": "2026-05-01", "instrument": "PMT-SOL-2026", "dwelling_type": "permanent", "water_source": "piped", "sanitation_facility": "flush", "cooking_fuel": "electricity", "electricity_access": "true", "income_source": "wage_work", "collected_by": "SRO enumerator", "profile_status": "current"}, "SRO-CORE"))
        band = "priority" if chunk % 7 == 0 else "standard" if chunk % 3 == 0 else "not_eligible"
        scores.append(add_meta({"scoring_id": f"SCOR-{h:05d}", "profile_id": f"SEP-{h:05d}", "scoring_rule": "PMT-SOL", "rule_version": "2026.1", "poverty_score": f"{25 + (chunk % 50):.2f}", "score_band": band, "valid_from": "2026-05-01", "valid_until": "2027-05-01", "scoring_status": "current"}, "SRO-CORE"))
        h += 1
    programs = [
        add_meta({"program_code": "CHILD_SUPPORT", "display_name": "Child Support Grant", "implementing_agency": "MoSD Programme MIS", "targeting_approach": "poverty_targeted", "conditionality_type": "none", "benefit_modality": "cash", "start_date": "2024-01-01", "end_date": ""}, "MOSD-MIS"),
        add_meta({"program_code": "OLD_AGE_GRANT", "display_name": "Old Age Grant", "implementing_agency": "MoSD Programme MIS", "targeting_approach": "categorical", "conditionality_type": "none", "benefit_modality": "cash", "start_date": "2024-01-01", "end_date": ""}, "MOSD-MIS"),
    ]
    decisions = [
        add_meta({"decision_id": "DEC-000001", "uin": uins["child_positive"], "household_id": "HH-002317", "program_code": "CHILD_SUPPORT", "eligibility_status": "eligible", "decision_basis": "SCOR-00001", "decision_date": "2026-06-15", "valid_until": "2027-06-15"}, "MOSD-MIS"),
        add_meta({"decision_id": "DEC-000002", "uin": uins["above_threshold_child"], "household_id": "HH-002319", "program_code": "CHILD_SUPPORT", "eligibility_status": "ineligible", "decision_basis": "SCOR-00003", "decision_date": "2026-06-15", "valid_until": "2027-06-15"}, "MOSD-MIS"),
        add_meta({"decision_id": "DEC-000003", "uin": uins["unregistered_child"], "household_id": "HH-002318", "program_code": "CHILD_SUPPORT", "eligibility_status": "pending", "decision_basis": "SCOR-00002", "decision_date": "2026-06-15", "valid_until": "2027-06-15"}, "MOSD-MIS"),
        add_meta({"decision_id": "DEC-000004", "uin": uins["duplicate_enrolled_child"], "household_id": "HH-002320", "program_code": "CHILD_SUPPORT", "eligibility_status": "eligible", "decision_basis": "SCOR-00004", "decision_date": "2026-06-15", "valid_until": "2027-06-15"}, "MOSD-MIS"),
        add_meta({"decision_id": "DEC-000005", "uin": uins["deceased_child_control"], "household_id": "HH-002321", "program_code": "CHILD_SUPPORT", "eligibility_status": "ineligible", "decision_basis": "SCOR-00005", "decision_date": "2026-06-15", "valid_until": "2027-06-15"}, "MOSD-MIS"),
    ]
    enrollments = [
        add_meta({"enrollment_id": "ENR-00001", "uin": uins["duplicate_enrolled_child"], "household_id": "HH-002320", "program_code": "CHILD_SUPPORT", "eligibility_decision_id": "DEC-000004", "enrollment_status": "active", "enrollment_date": "2026-05-20", "exit_date": "", "exit_reason": ""}, "MOSD-MIS")
    ]
    entitlements = [add_meta({"entitlement_id": "ENT-00001", "enrollment_id": "ENR-00001", "benefit_modality": "cash", "amount": "120.00", "currency": "XTS", "frequency": "monthly", "coverage_start": "2026-06-01", "coverage_end": "2026-12-31", "entitlement_status": "active"}, "MOSD-MIS")]
    payments = [add_meta({"payment_id": "PAY-00001", "entitlement_id": "ENT-00001", "pay_cycle": "2026-07", "amount": "120.00", "currency": "XTS", "payment_status": "scheduled", "delivery_channel": "mobile_money", "failure_reason": "", "is_reconciled": "false", "payment_date": "2026-07-25"}, "MOSD-MIS")]
    grievances = [add_meta({"grievance_id": "GRV-000001", "complainant_uin": uins["above_threshold_guardian"], "program_code": "CHILD_SUPPORT", "grievance_type": "eligibility", "grievance_status": "open", "submission_date": "2026-06-22", "resolution_date": ""}, "MOSD-MIS")]
    accounts = []
    periods = []
    awards = []
    instructions = []
    pol = []
    survivor = []
    for idx, key in enumerate(["deceased_pensioner", "survivor_spouse", "deceased_lag", "survivor_waits"], 1):
        account = f"SIPF-{idx:08d}"
        accounts.append(add_meta({"account_no": account, "uin": uins[key], "employer_business_id": "", "scheme": "old_age", "enrolment_date": "1990-01-01", "account_status": "in_payment", "accrued_qualifying_months": 360, "life_status": "deceased" if key == "deceased_pensioner" else "alive"}, "SIPF-CORE"))
        periods.append(add_meta({"contribution_period_id": f"SIPF-CP-{idx:06d}", "account_no": account, "employer_business_id": "", "period_month": "2024-12-01", "insurable_earnings": "800.00", "employee_contribution": "40.00", "employer_contribution": "40.00", "posting_status": "posted", "credited": "true"}, "SIPF-CORE"))
        award_no = f"SIPF-AWD-{idx:06d}"
        awards.append(add_meta({"award_no": award_no, "account_no": account, "beneficiary_uin": uins[key], "award_type": "old_age", "award_status": "in_payment" if key != "survivor_waits" else "pending_proof_of_life", "monthly_amount": "240.00", "currency": "XTS", "effective_date": "2010-01-01", "stop_date": "", "death_notified_drn": "DRN-2026-0301-00002" if key == "deceased_pensioner" else ""}, "SIPF-CORE"))
        instructions.append(add_meta({"instruction_id": f"SIPF-PI-{idx:06d}", "award_no": award_no, "beneficiary_uin": uins[key], "pay_period_month": "2026-07-01", "amount": "240.00", "currency": "XTS", "payment_status": "released" if key == "deceased_pensioner" else "scheduled", "hold_reason": "none", "released_at": "2026-07-01T10:00:00Z" if key == "deceased_pensioner" else ""}, "SIPF-CORE"))
        pol.append(add_meta({"check_id": f"SIPF-POL-{idx:06d}", "award_no": award_no, "beneficiary_uin": uins[key], "method": "civil_registry_crosscheck", "result": "deceased_found" if key == "deceased_pensioner" else "confirmed_alive", "checked_date": "2026-06-01", "next_due_date": "2026-06-01" if key == "survivor_waits" else "2026-12-01"}, "SIPF-CORE"))
    survivor.append(add_meta({"survivor_link_id": "SIPF-SL-000001", "deceased_uin": uins["deceased_pensioner"], "survivor_uin": uins["survivor_spouse"], "relationship": "spouse", "proof_mrn": "MRN-1970-0401-00001", "survivor_award_no": "", "link_status": "verified"}, "SIPF-CORE"))
    nagdi = build_nagdi(uins, by_uin, household_ids)
    return {
        "population_person": [add_meta(p, "NIA-SOLMARAID") for p in people],
        "persona_manifest": persona_manifest,
        "identity_document": docs,
        "consent_directive": consents,
        "civil_person": civil_people,
        "birth_event": births,
        "death_event": deaths,
        "marriage_event": marriages,
        "marriage_termination_event": terminations,
        "civil_status_record": statuses,
        "certificate": certificates,
        "relationship": relationships,
        "civil_identifier": identifiers,
        "household": households,
        "household_member": members,
        "socio_economic_profile": profiles,
        "scoring_event": scores,
        "program": programs,
        "eligibility_decision": decisions,
        "enrollment": enrollments,
        "entitlement": entitlements,
        "payment_event": payments,
        "grievance": grievances,
        "sipf_contribution_account": accounts,
        "sipf_contribution_period": periods,
        "sipf_pension_award": awards,
        "sipf_payment_instruction": instructions,
        "sipf_proof_of_life_check": pol,
        "sipf_survivor_link": survivor,
        **nagdi,
    }


def build_nagdi(uins: dict[str, str], by_uin: dict[str, dict[str, object]], household_ids: dict[str, str]) -> dict[str, list[dict[str, object]]]:
    farmer_keys = ["farmer_positive", "farmer_missing_auth", "farmer_risk_denied", "livestock_quarantine", "livestock_vaccination"]
    farmers = []
    identifiers = []
    holdings = []
    parcels = []
    tenure = []
    livestock_holdings = []
    premises = []
    herds = []
    animals = []
    for idx, key in enumerate(farmer_keys, 1):
        p = by_uin[uins[key]]
        farmer_id = PERSONAS[[x.key for x in PERSONAS].index(key)].farmer_alias
        farmers.append(add_meta({"farmer_id": farmer_id, "legacy_farmer_id": PERSONAS[[x.key for x in PERSONAS].index(key)].farmer_alias, "uin": p["uin"], "household_id": household_ids.get(key, ""), "given_name": p["given_name"], "family_name": p["family_name"], "district_code": p["district_code"], "farmer_status": "active", "registration_date": "2025-05-01"}, "NAGDI-CORE"))
        identifiers.append(add_meta({"identifier_id": f"FI-{idx:06d}", "farmer_id": farmer_id, "scheme": "uin", "value": p["uin"], "status": "active"}, "NAGDI-CORE"))
        holdings.append(add_meta({"holding_id": f"HOLD-{idx:06d}", "farmer_id": farmer_id, "district_code": p["district_code"], "holding_name": f"{p['family_name']} farm", "total_area_ha": f"{1.5 + idx:.2f}", "irrigated": "true" if idx % 2 else "false"}, "NAGDI-CORE"))
        parcels.append(add_meta({"parcel_ref": f"NAGDI-PARCEL-{idx:06d}", "holding_id": f"HOLD-{idx:06d}", "district_code": p["district_code"], "area_ha": f"{1.0 + idx / 2:.2f}", "centroid_lat": "-10.50", "centroid_lng": "79.50"}, "NAGDI-CORE"))
        tenure.append(add_meta({"tenure_claim_id": f"TC-{idx:06d}", "parcel_ref": f"NAGDI-PARCEL-{idx:06d}", "farmer_id": farmer_id, "land_tenure": "customary", "cadastre_parcel_id": "", "claim_status": "accepted"}, "NAGDI-CORE"))
        livestock_holdings.append(add_meta({"livestock_holding_id": f"LH-{idx:06d}", "farmer_id": farmer_id, "district_code": p["district_code"], "holding_status": "active"}, "NAGDI-CORE"))
        premises.append(add_meta({"premises_id": f"PRM-{idx:06d}", "livestock_holding_id": f"LH-{idx:06d}", "district_code": p["district_code"], "premises_type": "farm", "biosecurity_level": "standard"}, "NAGDI-CORE"))
        species = "cattle" if key != "livestock_quarantine" else "goat"
        herds.append(add_meta({"herd_id": f"HERD-{idx:06d}", "premises_id": f"PRM-{idx:06d}", "species": species, "head_count": 12 + idx, "health_status": "clear" if key != "livestock_quarantine" else "quarantine"}, "NAGDI-CORE"))
        animals.append(add_meta({"animal_id": f"ANI-{idx:06d}", "herd_id": f"HERD-{idx:06d}", "species": species, "tag_id": f"XS-TAG-{idx:06d}", "animal_status": "active"}, "NAGDI-CORE"))
    simple = {
        "FarmerIdentifiers": identifiers,
        "FarmerGroups": [add_meta({"group_id": "FG-000001", "group_name": "Anvela Climate Growers", "district_code": "XS-0103", "member_count": 2}, "NAGDI-CORE")],
        "DataUseAuthorizations": [add_meta({"authorization_id": "DUA-000001", "farmer_id": "FR-1001", "purpose_scope": "voucher-eligibility-review", "authorization_status": "authorized"}, "NAGDI-CORE")],
        "ChangeLog": [add_meta({"change_id": "CHG-000001", "entity_type": "Farmer", "entity_id": "FR-1001", "change_type": "created"}, "NAGDI-CORE")],
        "Holdings": holdings,
        "Parcels": parcels,
        "CropDeclarations": [add_meta({"crop_declaration_id": "CD-000001", "holding_id": "HOLD-000002", "crop": "maize", "season": "2026-A", "area_ha": "1.20"}, "NAGDI-CORE")],
        "TenureClaims": tenure,
        "Programs": [add_meta({"program_id": "AGP-000001", "program_name": "Climate Smart Voucher", "program_status": "active"}, "NAGDI-CORE")],
        "VoucherEntitlements": [add_meta({"voucher_id": "VE-000001", "farmer_id": "FR-1001", "program_id": "AGP-000001", "entitlement_status": "approved", "amount": "75.00", "currency": "XTS"}, "NAGDI-CORE")],
        "VoucherRedemptions": [add_meta({"redemption_id": "VR-000001", "voucher_id": "VE-000001", "supplier_id": "SUP-000001", "redemption_status": "pending"}, "NAGDI-CORE")],
        "ExtensionVisits": [add_meta({"visit_id": "EV-000001", "farmer_id": "FR-1001", "visit_date": "2026-06-12", "topic": "soil moisture"}, "NAGDI-CORE")],
        "Suppliers": [add_meta({"supplier_id": "SUP-000001", "supplier_name": "Solmara Seed Cooperative", "district_code": "XS-0103"}, "NAGDI-CORE")],
        "ProgramRules": [add_meta({"rule_id": "RULE-000001", "program_id": "AGP-000001", "rule_name": "risk-and-tenure-check", "rule_version": "2026.1"}, "NAGDI-CORE")],
        "InputPackages": [add_meta({"package_id": "PKG-000001", "package_name": "Drought maize starter", "crop": "maize"}, "NAGDI-CORE")],
        "BudgetAllocations": [add_meta({"allocation_id": "BA-000001", "program_id": "AGP-000001", "district_code": "XS-0103", "amount": "5000.00", "currency": "XTS"}, "NAGDI-CORE")],
        "RedemptionReconciliation": [add_meta({"reconciliation_id": "RR-000001", "redemption_id": "VR-000001", "reconciliation_status": "open"}, "NAGDI-CORE")],
        "Grievances": [add_meta({"grievance_id": "AG-GRV-000001", "farmer_id": "FR-1002", "grievance_status": "open", "grievance_type": "voucher_denial"}, "NAGDI-CORE")],
        "Sanctions": [add_meta({"sanction_id": "SAN-000001", "farmer_id": "FR-1002", "sanction_status": "inactive", "reason": "duplicate redemption warning"}, "NAGDI-CORE")],
        "DistrictClimateRisk": [add_meta({"risk_id": "DCR-000001", "district_code": "XS-0103", "risk_band": "high", "season": "2026-A"}, "NAGDI-CORE")],
        "RainfallObservations": [add_meta({"observation_id": "RAIN-000001", "district_code": "XS-0103", "observation_date": "2026-06-01", "rainfall_mm": "41.2"}, "NAGDI-CORE")],
        "MarketPrices": [add_meta({"price_id": "MP-000001", "district_code": "XS-0103", "commodity": "maize", "price": "14.20", "currency": "XTS"}, "NAGDI-CORE")],
        "CropCalendar": [add_meta({"calendar_id": "CC-000001", "district_code": "XS-0103", "crop": "maize", "planting_window": "2026-07"}, "NAGDI-CORE")],
        "AdvisoryRules": [add_meta({"advisory_rule_id": "AR-000001", "crop": "maize", "risk_band": "high", "advisory_text": "Use short-cycle seed"}, "NAGDI-CORE")],
        "VoucherMarketSizingCells": [add_meta({"cell_id": "VMSC-000001", "province_code": "XS-01", "crop": "maize", "eligible_farmers": 8}, "NAGDI-CORE")],
        "LivestockHoldings": livestock_holdings,
        "Premises": premises,
        "Herds": herds,
        "Animals": animals,
        "Vaccinations": [add_meta({"vaccination_id": "VAC-000001", "animal_id": "ANI-000004", "vaccine": "FMD", "vaccination_date": "2026-05-01"}, "NAGDI-CORE")],
        "QuarantineZones": [add_meta({"zone_id": "QZ-000001", "district_code": "XS-0403", "species": "goat", "zone_status": "active"}, "NAGDI-CORE")],
        "MovementApplications": [add_meta({"application_id": "MA-000001", "herd_id": "HERD-000004", "origin_premises_id": "PRM-000004", "destination_district_code": "XS-0402", "application_status": "approved"}, "NAGDI-CORE"), add_meta({"application_id": "MA-000002", "herd_id": "HERD-000005", "origin_premises_id": "PRM-000005", "destination_district_code": "XS-0402", "application_status": "quarantine_hold"}, "NAGDI-CORE")],
        "MovementPermits": [add_meta({"permit_id": "MPER-000001", "application_id": "MA-000001", "permit_status": "issued", "valid_until": "2026-08-01"}, "NAGDI-CORE")],
        "MovementEvents": [add_meta({"movement_event_id": "MEV-000001", "permit_id": "MPER-000001", "event_type": "departed", "event_date": "2026-07-02"}, "NAGDI-CORE")],
        "PurposePolicies": [add_meta({"policy_id": "PP-000001", "purpose": "voucher-eligibility-review", "requires_authorization": "true"}, "NAGDI-CORE")],
        "SourceSubmissions": [add_meta({"submission_id": "SS-000001", "source": "district_office", "submission_status": "accepted"}, "NAGDI-CORE")],
        "ValidationIssues": [add_meta({"issue_id": "VI-000001", "entity_id": "FR-1002", "issue_type": "near_threshold", "issue_status": "open"}, "NAGDI-CORE")],
        "DuplicateCandidates": [add_meta({"candidate_id": "DC-000001", "farmer_id": "FR-1005", "matched_farmer_id": "FR-1001", "match_basis": "name_address"}, "NAGDI-CORE")],
        "CorrectionRequests": [add_meta({"request_id": "CR-000001", "entity_id": "FR-1002", "request_status": "submitted"}, "NAGDI-CORE")],
        "VoucherEligibilitySnapshots": [add_meta({"snapshot_id": "VES-000001", "farmer_id": "FR-1001", "eligible": "true", "snapshot_date": "2026-07-04"}, "NAGDI-CORE")],
        "LivestockMovementSnapshots": [add_meta({"snapshot_id": "LMS-000001", "application_id": "MA-000002", "movement_allowed": "false", "reason": "species_quarantine"}, "NAGDI-CORE")],
        "MarketSizingCells": [add_meta({"cell_id": "MSC-000001", "province_code": "XS-01", "commodity": "maize", "farmers": 8}, "NAGDI-CORE")],
    }
    return {"Farmers": farmers, **simple}


def build_relay_projections(rows: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
    birth_by_person = {row["child_person_id"]: row for row in rows["birth_event"]}
    death_by_person = {row["deceased_person_id"]: row for row in rows["death_event"]}
    marriage_by_person: dict[object, dict[str, object]] = {}
    for row in rows["marriage_event"]:
        marriage_by_person[row["spouse_1_person_id"]] = row
        marriage_by_person[row["spouse_2_person_id"]] = row

    civil_projection = []
    for person in rows["civil_person"]:
        birth = birth_by_person.get(person["person_id"], {})
        death = death_by_person.get(person["person_id"], {})
        marriage = marriage_by_person.get(person["person_id"], {})
        civil_projection.append(add_meta({
            "person_id": person["person_id"],
            "uin": person["uin"],
            "given_name": person["given_name"],
            "family_name": person["family_name"],
            "birth_date": person["birth_date"],
            "birth_brn": birth.get("brn", ""),
            "death_drn": death.get("drn", ""),
            "marriage_mrn": marriage.get("mrn", ""),
            "deceased": str(person["life_status"] == "deceased").lower(),
            "death_date": person["death_date"],
            "cause_of_death": death.get("cause_of_death", ""),
            "district_code": person["birth_place_district_code"],
        }, "CRA-RELAY-PROJECTION"))

    people_by_uin = {row["uin"]: row for row in rows["population_person"]}
    profile_by_household = {row["household_id"]: row for row in rows["socio_economic_profile"]}
    score_by_profile = {row["profile_id"]: row for row in rows["scoring_event"]}
    members_by_household: dict[object, list[dict[str, object]]] = {}
    for row in rows["household_member"]:
        members_by_household.setdefault(row["household_id"], []).append(row)

    social_projection = []
    child_benefit_household_projection = []
    for household in rows["household"]:
        profile = profile_by_household[household["household_id"]]
        score = score_by_profile[profile["profile_id"]]
        child_count = 0
        for member in members_by_household.get(household["household_id"], []):
            person = people_by_uin[member["uin"]]
            if date.fromisoformat(str(person["birth_date"])) > date(2021, 7, 4):
                child_count += 1
        social_projection.append(add_meta({
            "household_id": household["household_id"],
            "head_uin": household["head_uin"],
            "district_code": household["district_code"],
            "poverty_score": score["poverty_score"],
            "poverty_band": score["score_band"],
            "member_count": household["household_size"],
            "child_under_5_count": child_count,
            "consent_status": "granted",
        }, "SRO-RELAY-PROJECTION"))
        for member in members_by_household.get(household["household_id"], []):
            if member["membership_status"] != "active":
                continue
            child_benefit_household_projection.append(add_meta({
                "uin": member["uin"],
                "poverty_band": score["score_band"],
            }, "SRO-CHILD-BENEFIT-PROJECTION"))

    active_enrollment_by_uin = {
        row["uin"]: row
        for row in rows["enrollment"]
        if row["enrollment_status"] == "active"
    }
    entitlement_by_enrollment = {row["enrollment_id"]: row for row in rows["entitlement"]}
    programme_projection = []
    for decision in rows["eligibility_decision"]:
        active = active_enrollment_by_uin.get(decision["uin"])
        entitlement = entitlement_by_enrollment.get(active["enrollment_id"], {}) if active else {}
        programme_projection.append(add_meta({
            "enrollment_id": decision["decision_id"],
            "uin": decision["uin"],
            "programme_id": decision["program_code"],
            "enrollment_status": active["enrollment_status"] if active else "none",
            "entitlement_status": entitlement.get("entitlement_status", "none"),
            "duplicate_flag": str(bool(active)).lower(),
            "benefit_start_date": active["enrollment_date"] if active else "",
        }, "MOSD-RELAY-PROJECTION"))

    survivor_by_deceased = {row["deceased_uin"]: row for row in rows["sipf_survivor_link"]}
    account_by_no = {row["account_no"]: row for row in rows["sipf_contribution_account"]}
    instruction_by_award = {row["award_no"]: row for row in rows["sipf_payment_instruction"]}
    pension_projection = []
    for award in rows["sipf_pension_award"]:
        account = account_by_no[award["account_no"]]
        survivor = survivor_by_deceased.get(award["beneficiary_uin"], {})
        instruction = instruction_by_award.get(award["award_no"], {})
        pension_projection.append(add_meta({
            "pension_case_id": award["award_no"],
            "pensioner_uin": award["beneficiary_uin"],
            "spouse_uin": survivor.get("survivor_uin", ""),
            "marriage_mrn": survivor.get("proof_mrn", ""),
            "pension_status": award["award_status"],
            "payment_status": "active" if instruction.get("payment_status") in {"released", "scheduled"} else instruction.get("payment_status", ""),
            "survivor_eligible": str(survivor.get("link_status") == "verified").lower(),
            "last_payment_date": str(instruction.get("released_at", ""))[:10],
            "account_life_status": account["life_status"],
        }, "SIPF-RELAY-PROJECTION"))

    farmers_by_id = {row["farmer_id"]: row for row in rows["Farmers"]}
    farmer_projection = []
    for farmer_id, farmer in farmers_by_id.items():
        farmer_projection.append(add_meta({
            "farmer_id": farmer_id,
            "uin": farmer["uin"],
            "district_code": farmer["district_code"],
            "farmer_registered": str(farmer["farmer_status"] == "active").lower(),
            "data_use_authorized": str(farmer_id != "FR-1002").lower(),
            "active_smallholder_farmer": "true",
            "active_farm_parcel": "true",
            "crop_declared_for_season": "true",
            "district_climate_risk_active": str(farmer_id != "FR-1003").lower(),
            "voucher_entitlement_current": str(farmer_id == "FR-1001").lower(),
            "voucher_not_redeemed": str(farmer_id != "FR-1003").lower(),
        }, "NAGDI-RELAY-PROJECTION"))

    farmer_by_livestock_holding = {
        row["livestock_holding_id"]: row["farmer_id"]
        for row in rows["LivestockHoldings"]
    }
    farmer_by_premises = {
        row["premises_id"]: farmer_by_livestock_holding[row["livestock_holding_id"]]
        for row in rows["Premises"]
    }
    livestock_projection = []
    for herd in rows["Herds"]:
        farmer_id = farmer_by_premises[herd["premises_id"]]
        livestock_projection.append(add_meta({
            "herd_id": herd["herd_id"],
            "farmer_id": farmer_id,
            "species": herd["species"],
            "registered_livestock_holder": "true",
            "registered_herd": "true",
            "herd_vaccination_current": str(farmer_id != "FR-1005").lower(),
            "origin_district_not_quarantined_for_species": str(farmer_id != "FR-1004").lower(),
            "destination_district_open": "true",
            "no_conflicting_open_movement_permit": "true",
        }, "NAGDI-RELAY-PROJECTION"))

    return {
        "civil_person_projection": civil_projection,
        "social_registry_household": social_projection,
        "child_benefit_household": child_benefit_household_projection,
        "programme_mis_enrollment": programme_projection,
        "pension_case": pension_projection,
        "farmer_voucher": farmer_projection,
        "livestock_movement": livestock_projection,
    }


def admin_rows() -> list[dict[str, object]]:
    rows = [add_meta({"admin_code": "XS", "admin_level": "country", "admin_name": "Republic of Solmara", "parent_admin_code": "", "valid_from": "2026-01-01", "valid_until": ""}, "SOLMARA-GEO")]
    rows.extend(add_meta({"admin_code": c, "admin_level": "province", "admin_name": n, "parent_admin_code": "", "valid_from": "2026-01-01", "valid_until": ""}, "SOLMARA-GEO") for c, n, _ in PROVINCES)
    rows.extend(add_meta({"admin_code": c, "admin_level": "district", "admin_name": n, "parent_admin_code": p, "valid_from": "2026-01-01", "valid_until": ""}, "SOLMARA-GEO") for c, n, p in DISTRICTS)
    rows.append(add_meta({"admin_code": "XS-0203-OLD", "admin_level": "district_version", "admin_name": "Velcor old boundary", "parent_admin_code": "XS-02", "valid_from": "2024-01-01", "valid_until": "2025-12-31"}, "SOLMARA-GEO"))
    return rows


def write_geo(root: Path) -> None:
    country, provinces, districts = geo_features()
    for name, features in [("country", country), ("provinces", provinces), ("districts", districts)]:
        write_text(root / "geo" / f"{name}.geojson", json.dumps({"type": "FeatureCollection", "features": features}, indent=2, sort_keys=True) + "\n")
    write_text(root / "generator/output/shared/districts-edr.geojson", json.dumps({"type": "FeatureCollection", "features": [f for f in districts if f["properties"]["admin_level"] == "district"]}, indent=2, sort_keys=True) + "\n")


def checksum_manifest(root: Path) -> None:
    targets = []
    for base in ["generator/output", "geo", "ministries"]:
        for path in sorted((root / base).rglob("*")):
            if path.is_file() and path.name != "checksums.sha256":
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                targets.append(f"{digest}  {path.relative_to(root).as_posix()}")
    write_text(root / "generator/output/checksums.sha256", "\n".join(targets) + "\n")


def clean_outputs(root: Path) -> None:
    for base, names in TABLES.items():
        folder = root / base
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            suffix = "" if name.endswith(".sql") else ".csv"
            path = folder / f"{name}{suffix}"
            if path.exists():
                path.unlink()
    for path in [root / "generator/output/shared", root / "geo"]:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def generate(root: Path) -> None:
    clean_outputs(root)
    rows = build_rows(root)
    rows.update(build_relay_projections(rows))
    for table in ["civil_person", "birth_event", "death_event", "marriage_event", "marriage_termination_event", "civil_status_record", "certificate", "relationship", "civil_identifier", "civil_person_projection"]:
        write_csv(root / "ministries/interior-civil/fixtures" / f"{table}.csv", rows[table])
    for table in ["population_person", "identity_document", "consent_directive"]:
        write_csv(root / "ministries/interior-population/fixtures" / f"{table}.csv", rows[table])
    write_text(root / "ministries/interior-population/fixtures/001-schema.sql", "create table population_person (uin text primary key, person_id text, legacy_nid text, given_name text, family_name text, birth_date date, sex text, district_code text, address_area text, settlement_type text, identity_status text, pending_merge_with_uin text, match_basis text, alive boolean, birth_brn text, updated_at timestamptz, observed_at timestamptz, source_system text);\n")
    write_text(root / "ministries/interior-population/fixtures/002-load.sql", "copy population_person from '/docker-entrypoint-initdb.d/population_person.csv' with (format csv, header true);\n")
    for table in ["household", "household_member", "socio_economic_profile", "scoring_event", "program", "eligibility_decision", "enrollment", "entitlement", "payment_event", "grievance", "social_registry_household", "child_benefit_household", "programme_mis_enrollment"]:
        write_csv(root / "ministries/social-development/fixtures" / f"{table}.csv", rows[table])
    for table in ["sipf_contribution_account", "sipf_contribution_period", "sipf_pension_award", "sipf_payment_instruction", "sipf_proof_of_life_check", "sipf_survivor_link", "pension_case"]:
        write_csv(root / "ministries/labour-pensions/fixtures" / f"{table}.csv", rows[table])
    for table in TABLES["ministries/agriculture-nagdi/fixtures"]:
        write_csv(root / "ministries/agriculture-nagdi/fixtures" / f"{table}.csv", rows[table])
    write_csv(root / "generator/output/shared/admin_areas.csv", admin_rows())
    write_csv(root / "generator/output/shared/personas.csv", rows["persona_manifest"])
    write_geo(root)
    checksum_manifest(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    generate(args.root.resolve())


if __name__ == "__main__":
    main()
