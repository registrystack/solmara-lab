from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent

EXPECTED = {
    "cra": {
        "civil-person": {
            "death-by-uin": ("cra-pension-evidence", "solmara:relay:cra:death-by-uin"),
            "citizen-link-by-uin": ("cra-citizen-evidence", "solmara:relay:cra:citizen-link-by-uin"),
        }
    },
    "nia": {"population-person": {"esignet-userinfo": ("nia-esignet", "solmara:relay:nia:esignet-userinfo")}},
    "mosd": {"beneficiary-enrolment": {"by-uin": ("mosd-child-benefit-evidence", "solmara:relay:mosd:by-uin")}},
    "sipf": {
        "pension-payment": {"by-pensioner-uin": ("sipf-pension-evidence", "solmara:relay:sipf:by-pensioner-uin")},
        "survivor-case": {"by-spouse-uin": ("sipf-survivor-evidence", "solmara:relay:sipf:by-spouse-uin")},
    },
    "nagdi": {
        "farmer": {"voucher-by-farmer-id": ("nagdi-voucher-evidence", "solmara:relay:nagdi:voucher-by-farmer-id")},
        "livestock-herd": {"movement-by-farmer-id": ("nagdi-livestock-evidence", "solmara:relay:nagdi:movement-by-farmer-id")},
    },
}


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def lookup_map(contract: dict) -> dict[tuple[str, str], dict]:
    result = {}
    for resource in contract["resources"]:
        operations = resource["operations"]
        if operations.get("list") or operations.get("read") or operations.get("searches"):
            raise AssertionError(f"{resource['id']} declares a forbidden enumerating operation")
        for lookup in operations.get("lookups", []):
            result[(resource["id"], lookup["id"])] = lookup
    return result


class RelayProjectContracts(unittest.TestCase):
    def test_exact_authority_owned_topology_and_operation_inventory(self) -> None:
        self.assertEqual(set(EXPECTED), {path.name for path in ROOT.iterdir() if path.is_dir() and not path.name.startswith("__")})
        for authority, resources in EXPECTED.items():
            contract = load(ROOT / authority / "registry.yaml")
            actual = lookup_map(contract)
            expected = {(resource, lookup) for resource, lookups in resources.items() for lookup in lookups}
            self.assertEqual(set(actual), expected)
            for resource in contract["resources"]:
                lookups = resource["operations"]["lookups"]
                self.assertEqual(len(resource["disclosureProfiles"]), len(lookups))
                for lookup in lookups:
                    profiles = lookup["accessProfiles"]
                    self.assertEqual(len(profiles), 1)
                    self.assertIn(lookup["defaultAccessProfile"], profiles)

    def test_scopes_and_authorization_principals_are_operation_specific(self) -> None:
        for authority, resources in EXPECTED.items():
            contract = load(ROOT / authority / "registry.yaml")
            journey = load(ROOT / authority / "expected-http.yaml")
            actual = lookup_map(contract)
            for resource, lookups in resources.items():
                for lookup_id, (principal, scope) in lookups.items():
                    lookup = actual[(resource, lookup_id)]
                    profile = next(iter(lookup["accessProfiles"].values()))
                    self.assertEqual(profile["access"]["scope"], scope)
                    matching = [fixture for fixture in journey["authorizations"].values() if fixture["principal"] == principal and scope in fixture["scopes"]]
                    self.assertTrue(matching, f"{authority}/{lookup_id} lacks its dedicated principal fixture")

    def test_runtime_is_container_bound_shared_mint_and_fail_closed_audit(self) -> None:
        for authority in EXPECTED:
            runtime = load(ROOT / authority / "runtime.yaml")
            self.assertEqual(runtime["server"]["bind"], "0.0.0.0:8080")
            self.assertEqual(runtime["packagePath"], f"/etc/relay/{authority}/package")
            self.assertEqual(runtime["sources"][authority]["path"], f"/var/lib/relay/source/{authority}.sqlite")
            issuer = runtime["authentication"]["issuer"]
            self.assertEqual(
                issuer["discoveryUrl"],
                "https://mint.solmara.registrystack.org/.well-known/openid-configuration",
            )
            self.assertEqual(issuer["audience"], "solmara-runtime")
            self.assertEqual(issuer["algorithms"], ["ES256"])
            self.assertEqual(runtime["audit"]["sink"], "/var/lib/relay/audit/audit.jsonl")
            self.assertTrue(runtime["audit"]["integrityKeyRef"].startswith("secret:env/"))

    def test_fixture_shorthand_maps_to_real_nested_selector_body(self) -> None:
        for authority in EXPECTED:
            journey = load(ROOT / authority / "expected-http.yaml")
            for step in journey["steps"]:
                request = step["request"]
                if request["method"] != "POST":
                    continue
                shorthand = request["body"]
                self.assertNotIn("selectors", shorthand)
                wire = json.loads(json.dumps({"selectors": shorthand}, separators=(",", ":")))
                self.assertEqual(wire, {"selectors": shorthand})

    def test_each_lookup_has_behavioral_boundary_coverage(self) -> None:
        for authority, resources in EXPECTED.items():
            steps = [step["id"] for step in load(ROOT / authority / "expected-http.yaml")["steps"]]
            fixture_sql = (ROOT / authority / "fixture.sql").read_text()
            lookup_count = sum(len(lookups) for lookups in resources.values())
            for lookups in resources.values():
                for lookup_id in lookups:
                    prefix = {
                        "death-by-uin": "death-",
                        "citizen-link-by-uin": "citizen-",
                        "esignet-userinfo": "userinfo-",
                        "by-uin": "",
                        "by-pensioner-uin": "pension-",
                        "by-spouse-uin": "survivor-",
                        "voucher-by-farmer-id": "voucher-",
                        "movement-by-farmer-id": "livestock-",
                    }[lookup_id]
                    for suffix in ("success", "fields-minimum", "wrong-scope", "wrong-purpose", "malformed-selector", "no-match", "invalid-row"):
                        self.assertTrue(
                            f"{prefix}{suffix}" in steps or (lookup_count == 1 and suffix in steps),
                            f"{authority}/{lookup_id} lacks {suffix}",
                        )
            self.assertTrue(any("no-list" in step for step in steps))
            # The publisher's UNIQUE selectors make ambiguity structurally impossible for
            # every lookup except NAgDI livestock, whose two-row case is exercised over HTTP.
            if authority == "nagdi":
                self.assertIn("livestock-ambiguous", steps)
            self.assertIn("UNIQUE", fixture_sql)

    def test_classification_reviews_bind_real_inventory_digests(self) -> None:
        zero = "sha256:" + "0" * 64
        for authority in EXPECTED:
            review = load(ROOT / authority / "governance" / "classification-review.yaml")
            self.assertEqual(review["method"], "manual")
            self.assertEqual(review["status"], "reviewed")
            self.assertNotEqual(review["classificationInventoryDigest"], zero)

    def test_cra_birth_fields_are_never_disclosed(self) -> None:
        contract = load(ROOT / "cra" / "registry.yaml")
        resource = contract["resources"][0]
        disclosed = {name for profile in resource["disclosureProfiles"].values() for name in profile["properties"]}
        self.assertTrue({"birthDateInternal", "birthRegistrationNumberInternal"}.isdisjoint(disclosed))
        self.assertEqual(resource["disclosureProfiles"]["death-fact"]["properties"], ["deceased"])
        death = next(item for item in resource["operations"]["lookups"] if item["id"] == "death-by-uin")
        self.assertEqual(set(death["requestBody"]["selectors"]), {"uin"})
        steps = {step["id"]: step for step in load(ROOT / "cra" / "expected-http.yaml")["steps"]}
        self.assertEqual(steps["death-success"]["expect"]["domainDataValues"], {"deceased": True})
        self.assertEqual(steps["death-living-success"]["expect"]["domainDataValues"], {"deceased": False})


if __name__ == "__main__":
    unittest.main()
