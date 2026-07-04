from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from solmara_lab.generate import generate, valid_uin

REPO_ROOT = Path(__file__).resolve().parents[2]


def read_csv(root: Path, rel: str) -> list[dict[str, str]]:
    with (root / rel).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def digest_tree(root: Path) -> dict[str, str]:
    digests = {}
    for base in ["generator/output", "geo", "ministries"]:
        for path in sorted((root / base).rglob("*")):
            if path.is_file():
                digests[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def seed_workspace(target: Path) -> None:
    for name in ["generator", "geo", "ministries"]:
        shutil.copytree(REPO_ROOT / name, target / name, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        seed_workspace(cls.root)
        generate(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_repeatability(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_root = Path(first)
            second_root = Path(second)
            seed_workspace(first_root)
            seed_workspace(second_root)
            generate(first_root)
            generate(second_root)
            self.assertEqual(digest_tree(first_root), digest_tree(second_root))

    def test_referential_invariants(self) -> None:
        people = read_csv(self.root, "ministries/interior-population/fixtures/population_person.csv")
        uins = {row["uin"] for row in people}
        civil_people = read_csv(self.root, "ministries/interior-civil/fixtures/civil_person.csv")
        civil_ids = {row["person_id"] for row in civil_people}
        births = read_csv(self.root, "ministries/interior-civil/fixtures/birth_event.csv")
        deaths = read_csv(self.root, "ministries/interior-civil/fixtures/death_event.csv")
        marriages = read_csv(self.root, "ministries/interior-civil/fixtures/marriage_event.csv")
        brns = {row["brn"] for row in births}
        drns = {row["drn"] for row in deaths}
        mrns = {row["mrn"] for row in marriages}

        for row in civil_people:
            self.assertIn(row["uin"], uins)
        for row in births:
            self.assertIn(row["child_person_id"], civil_ids)
            self.assertEqual(row["facility_id"], "")
        for row in deaths:
            self.assertIn(row["deceased_person_id"], civil_ids)
            self.assertEqual(row["facility_id"], "")
        for row in read_csv(self.root, "ministries/interior-civil/fixtures/civil_status_record.csv"):
            if row["record_type"] == "birth":
                self.assertIn(row["registration_number"], brns)
            if row["record_type"] == "death":
                self.assertIn(row["registration_number"], drns)
        for row in people:
            if row["birth_brn"]:
                self.assertIn(row["birth_brn"], brns)

        households = {row["household_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/household.csv")}
        profiles = {row["profile_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/socio_economic_profile.csv")}
        scores = {row["scoring_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/scoring_event.csv")}
        decisions = {row["decision_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/eligibility_decision.csv")}
        enrollments = {row["enrollment_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/enrollment.csv")}
        entitlements = {row["entitlement_id"] for row in read_csv(self.root, "ministries/social-development/fixtures/entitlement.csv")}
        for row in read_csv(self.root, "ministries/social-development/fixtures/household_member.csv"):
            self.assertIn(row["uin"], uins)
            self.assertIn(row["household_id"], households)
        for row in read_csv(self.root, "ministries/social-development/fixtures/scoring_event.csv"):
            self.assertIn(row["profile_id"], profiles)
        for row in read_csv(self.root, "ministries/social-development/fixtures/eligibility_decision.csv"):
            self.assertIn(row["uin"], uins)
            if row["household_id"]:
                self.assertIn(row["household_id"], households)
            self.assertIn(row["decision_basis"], scores)
        for row in read_csv(self.root, "ministries/social-development/fixtures/enrollment.csv"):
            self.assertIn(row["uin"], uins)
            self.assertIn(row["eligibility_decision_id"], decisions)
        for row in read_csv(self.root, "ministries/social-development/fixtures/entitlement.csv"):
            self.assertIn(row["enrollment_id"], enrollments)
        for row in read_csv(self.root, "ministries/social-development/fixtures/payment_event.csv"):
            self.assertIn(row["entitlement_id"], entitlements)

        accounts = {row["account_no"] for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_contribution_account.csv")}
        awards = {row["award_no"] for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_pension_award.csv")}
        for rel in [
            "sipf_contribution_account",
            "sipf_pension_award",
            "sipf_payment_instruction",
            "sipf_proof_of_life_check",
        ]:
            for row in read_csv(self.root, f"ministries/labour-pensions/fixtures/{rel}.csv"):
                if "beneficiary_uin" in row:
                    self.assertIn(row["beneficiary_uin"], uins)
        for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_contribution_period.csv"):
            self.assertIn(row["account_no"], accounts)
            self.assertEqual(row["employer_business_id"], "")
        for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_pension_award.csv"):
            self.assertIn(row["account_no"], accounts)
            if row["death_notified_drn"]:
                self.assertIn(row["death_notified_drn"], drns)
        for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_payment_instruction.csv"):
            self.assertIn(row["award_no"], awards)
        for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_survivor_link.csv"):
            self.assertIn(row["deceased_uin"], uins)
            self.assertIn(row["survivor_uin"], uins)
            self.assertIn(row["proof_mrn"], mrns)

        for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/Farmers.csv"):
            self.assertIn(row["uin"], uins)
            if row["household_id"]:
                self.assertIn(row["household_id"], households)
        farmer_ids = {
            row["farmer_id"]
            for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/Farmers.csv")
        }
        for fixture in (self.root / "ministries/agriculture-nagdi/fixtures").glob("*.csv"):
            for row in read_csv(self.root, fixture.relative_to(self.root).as_posix()):
                for field in ("farmer_id", "matched_farmer_id"):
                    if row.get(field):
                        self.assertIn(row[field], farmer_ids, f"{fixture.name}:{field}")
                if row.get("entity_id", "").startswith("FR-"):
                    self.assertIn(row["entity_id"], farmer_ids, f"{fixture.name}:entity_id")
        for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/TenureClaims.csv"):
            self.assertEqual(row["cadastre_parcel_id"], "")

    def test_id_formats_and_seeded_edges(self) -> None:
        people = read_csv(self.root, "ministries/interior-population/fixtures/population_person.csv")
        for row in people:
            self.assertTrue(valid_uin(row["uin"]), row["uin"])
        self.assertTrue(any(row["legacy_nid"] == "NID-1008" and row["birth_brn"] == "" for row in people))
        self.assertTrue(any(row["legacy_nid"] == "NID-1010" and row["identity_status"] == "deceased" for row in people))
        self.assertTrue(any(row["legacy_nid"] == "NID-2001" and row["identity_status"] == "deceased" for row in people))

        for row in read_csv(self.root, "ministries/interior-civil/fixtures/birth_event.csv"):
            self.assertRegex(row["brn"], r"^BRN-\d{4}-\d{4}-\d{5}$")
        for row in read_csv(self.root, "ministries/interior-civil/fixtures/death_event.csv"):
            self.assertRegex(row["drn"], r"^DRN-\d{4}-\d{4}-\d{5}$")
        for row in read_csv(self.root, "ministries/interior-civil/fixtures/marriage_event.csv"):
            self.assertRegex(row["mrn"], r"^MRN-\d{4}-\d{4}-\d{5}$")
        for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/Farmers.csv"):
            self.assertRegex(row["farmer_id"], r"^FR-\d+$")
        self.assertTrue(any(row["farmer_id"] == "FR-1001" for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/Farmers.csv")))
        self.assertTrue(any(row["payment_status"] == "released" and row["beneficiary_uin"] for row in read_csv(self.root, "ministries/labour-pensions/fixtures/sipf_payment_instruction.csv")))
        self.assertTrue(any(row["consent_status"] == "withdrawn" for row in read_csv(self.root, "ministries/interior-population/fixtures/consent_directive.csv")))
        personas = read_csv(self.root, "generator/output/shared/personas.csv")
        self.assertGreaterEqual(len(personas), 20)
        self.assertTrue(any(row["persona_id"] == "deceased_pensioner" and row["roster_primary_id"] == "2300109568" for row in personas))
        self.assertTrue(any(row["persona_id"] == "livestock_vaccination" and row["roster_primary_id"] == "FR-1005" for row in personas))

    def test_relay_projection_edges(self) -> None:
        civil = {
            row["uin"]: row
            for row in read_csv(self.root, "ministries/interior-civil/fixtures/civil_person_projection.csv")
        }
        self.assertEqual(civil["2300010248"]["birth_brn"], "BRN-2022-0101-00001")
        self.assertEqual(civil["2300109568"]["deceased"], "true")
        self.assertEqual(civil["2300109568"]["cause_of_death"], "natural causes")

        social = {
            row["head_uin"]: row
            for row in read_csv(self.root, "ministries/social-development/fixtures/social_registry_household.csv")
        }
        self.assertEqual(social["2300027390"]["poverty_band"], "priority")
        self.assertEqual(social["2300045650"]["poverty_band"], "not_eligible")

        programme = {
            row["uin"]: row
            for row in read_csv(self.root, "ministries/social-development/fixtures/programme_mis_enrollment.csv")
        }
        self.assertEqual(programme["2300010248"]["duplicate_flag"], "false")
        self.assertEqual(programme["2300054788"]["duplicate_flag"], "true")

        pensions = {
            row["pensioner_uin"]: row
            for row in read_csv(self.root, "ministries/labour-pensions/fixtures/pension_case.csv")
        }
        self.assertEqual(pensions["2300109568"]["payment_status"], "active")
        self.assertEqual(pensions["2300109568"]["survivor_eligible"], "true")

        vouchers = {
            row["farmer_id"]: row
            for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/farmer_voucher.csv")
        }
        self.assertEqual(vouchers["FR-1001"]["data_use_authorized"], "true")
        self.assertEqual(vouchers["FR-1002"]["data_use_authorized"], "false")
        self.assertEqual(vouchers["FR-1003"]["district_climate_risk_active"], "false")

        livestock = {
            row["farmer_id"]: row
            for row in read_csv(self.root, "ministries/agriculture-nagdi/fixtures/livestock_movement.csv")
        }
        self.assertEqual(livestock["FR-1001"]["origin_district_not_quarantined_for_species"], "true")
        self.assertEqual(livestock["FR-1004"]["origin_district_not_quarantined_for_species"], "false")
        self.assertEqual(livestock["FR-1005"]["herd_vaccination_current"], "false")

    def test_fiction_lint(self) -> None:
        legacy_country_terms = [
            "Philip" + "pines",
            "Zam" + "bia",
            "Fara" + "jaland",
            "Sri " + "Lanka",
            "Co" + "cos",
            "Diego " + "Garcia",
        ]
        forbidden = re.compile(r"\b(" + "|".join(map(re.escape, legacy_country_terms)) + r")\b|@gmail\.com|@yahoo\.com|\.gov\.ph", re.IGNORECASE)
        for base in ["generator/output", "geo", "ministries"]:
            for path in (self.root / base).rglob("*"):
                if path.is_file():
                    text = path.read_text(encoding="utf-8")
                    self.assertIsNone(forbidden.search(text), path)
                    self.assertNotIn("country: " + "ZZ", text)
        admin = read_csv(self.root, "generator/output/shared/admin_areas.csv")
        self.assertEqual(admin[0]["admin_code"], "XS")
        self.assertTrue(all(row["admin_code"] == "XS" or row["admin_code"].startswith("XS-") for row in admin))

    def test_geo_topology_sanity(self) -> None:
        country = json.loads((self.root / "geo/country.geojson").read_text(encoding="utf-8"))["features"]
        provinces = json.loads((self.root / "geo/provinces.geojson").read_text(encoding="utf-8"))["features"]
        districts = [
            f for f in json.loads((self.root / "geo/districts.geojson").read_text(encoding="utf-8"))["features"]
            if f["properties"]["admin_level"] == "district"
        ]
        self.assertEqual(len(country), 1)
        self.assertEqual(len(provinces), 4)
        self.assertEqual(len(districts), 12)
        for feature in country + provinces + districts:
            props = feature["properties"]
            self.assertEqual(props["crs"], "EPSG:4326")
            coords = feature["geometry"]["coordinates"][0]
            self.assertEqual(coords[0], coords[-1])
            for lon, lat in coords:
                self.assertGreater(lon, 78.9)
                self.assertLess(lon, 80.3)
                self.assertGreater(lat, -11.1)
                self.assertLess(lat, -9.7)

        def area(feature: dict[str, object]) -> float:
            coords = feature["geometry"]["coordinates"][0]
            total = 0.0
            for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
                total += x1 * y2 - x2 * y1
            return abs(total) / 2

        country_area = area(country[0])
        province_area = sum(area(f) for f in provinces)
        district_area = sum(area(f) for f in districts)
        self.assertAlmostEqual(country_area, province_area, places=9)
        self.assertAlmostEqual(province_area, district_area, places=9)
        province_codes = {f["properties"]["admin_code"] for f in provinces}
        self.assertTrue(all(f["properties"]["parent_admin_code"] in province_codes for f in districts))


if __name__ == "__main__":
    unittest.main()
