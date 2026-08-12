from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata" / "public" / "metadata"


class AuthorityMetadataContractTests(unittest.TestCase):
    def test_data_services_publish_evidence_and_exact_records_routes(self) -> None:
        catalog = json.loads((METADATA / "catalog.json").read_text(encoding="utf-8"))
        evidence = next(
            service for service in catalog["data_services"]
            if service["id"] == "registry-evidence-api"
        )
        self.assertEqual(
            evidence["endpoint_url"],
            "https://evidence.solmara.registrystack.org/v1/evidence",
        )

        records_services = [
            service
            for service in catalog["data_services"]
            if service["id"].endswith("-records-api")
        ]

        self.assertEqual(len(records_services), 8)
        for service in records_services:
            with self.subTest(service=service["id"]):
                self.assertIn("/v1/datasets/", service["iri"])
                self.assertTrue(service["iri"].endswith("/records"))
                self.assertEqual(service["endpoint_url"], service["iri"])
                self.assertTrue(
                    service["endpoint_description"].endswith("/openapi.json")
                )

    def test_authority_offerings_publish_evaluation_and_discovery_routes(self) -> None:
        document = json.loads(
            (METADATA / "evidence-offerings.json").read_text(encoding="utf-8")
        )
        authority_offerings = [
            offering
            for offering in document["offerings"]
            if offering["access"]["kind"] == "evidence-verification-api"
        ]

        self.assertEqual(len(authority_offerings), 8)
        for offering in authority_offerings:
            with self.subTest(offering=offering["id"]):
                access = offering["access"]
                self.assertEqual(
                    access["endpoint_url"],
                    "https://evidence.solmara.registrystack.org/v1/evidence",
                )
                self.assertEqual(
                    access["discovery_url"],
                    "https://evidence.solmara.registrystack.org/v1/evidence-definitions",
                )

    def test_offering_purposes_match_evidence_requirements(self) -> None:
        document = json.loads(
            (METADATA / "evidence-offerings.json").read_text(encoding="utf-8")
        )
        offerings = {offering["id"]: offering for offering in document["offerings"]}

        self.assertEqual(
            offerings["sipf-pensions-pension-case-offering"]["purposes"],
            [
                "https://id.registrystack.org/solmara/purpose/pension-payment-review",
                "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination",
            ],
        )
        self.assertEqual(
            offerings["nagdi-agriculture-farmer-voucher-offering"]["purposes"],
            ["https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"],
        )
        self.assertEqual(
            offerings["nagdi-agriculture-livestock-movement-offering"]["purposes"],
            ["https://id.registrystack.org/solmara/purpose/livestock-movement-control"],
        )

        self.assertNotIn(
            "solmara.child-benefit.authority-predicate-collection", offerings
        )

    def test_cra_offerings_publish_only_the_supported_uin_lookup(self) -> None:
        for offering_id in (
            "cra-birth-registration-offering",
            "cra-death-registration-offering",
        ):
            with self.subTest(offering=offering_id):
                offering = json.loads(
                    (METADATA / "evidence-offerings" / f"{offering_id}.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(offering["lookup_keys"], ["uin"])

    def test_survivor_example_targets_the_surviving_spouse(self) -> None:
        request = (
            ROOT
            / "requests"
            / "registry-lab"
            / "30 - Pension Survivor"
            / "03 - Read survivor eligibility.bru"
        ).read_text(encoding="utf-8")

        self.assertIn('"values": { "uin": "2300118698" }', request)
        self.assertNotIn('"value": "2300109568"', request)


if __name__ == "__main__":
    unittest.main()
