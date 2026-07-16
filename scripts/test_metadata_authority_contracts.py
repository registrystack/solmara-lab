from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata" / "public" / "metadata"


class AuthorityMetadataContractTests(unittest.TestCase):
    def test_notary_data_services_publish_real_runtime_routes(self) -> None:
        catalog = json.loads((METADATA / "catalog.json").read_text(encoding="utf-8"))
        authority_services = [
            service
            for service in catalog["data_services"]
            if service["id"].endswith("-notary-api")
        ]

        self.assertEqual(len(authority_services), 6)
        for service in authority_services:
            with self.subTest(service=service["id"]):
                self.assertTrue(service["iri"].endswith("/v1/evaluations"))
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
                self.assertTrue(access["endpoint_url"].endswith("/v1/evaluations"))
                self.assertTrue(
                    access["discovery_url"].endswith("/.well-known/evidence-service")
                )

    def test_offering_purposes_match_notary_services(self) -> None:
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

        self.assertIn('"value": "2300118698"', request)
        self.assertNotIn('"value": "2300109568"', request)


if __name__ == "__main__":
    unittest.main()
