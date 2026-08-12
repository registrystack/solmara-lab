from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata" / "public" / "metadata"


class AuthorityMetadataContractTests(unittest.TestCase):
    def test_six_authority_evidence_services_publish_real_runtime_routes(self) -> None:
        catalog = json.loads((METADATA / "catalog.json").read_text(encoding="utf-8"))
        authority_services = [
            service
            for service in catalog["data_services"]
            if service["id"].endswith("-evidence-api")
        ]

        self.assertEqual(len(authority_services), 6)
        self.assertEqual(
            {service["id"] for service in authority_services},
            {
                "cra-evidence-api",
                "nia-evidence-api",
                "sro-evidence-api",
                "mosd-programme-evidence-api",
                "sipf-evidence-api",
                "nagdi-evidence-api",
            },
        )
        for service in authority_services:
            with self.subTest(service=service["id"]):
                self.assertTrue(service["iri"].endswith("/v1/evidence"))
                self.assertEqual(service["endpoint_url"], service["iri"])
                self.assertTrue(
                    service["endpoint_description"].endswith(
                        "/v1/evidence-definitions"
                    )
                )
                self.assertEqual(
                    service["conforms_to"],
                    "https://id.registrystack.org/spec/registry-evidence/v1",
                )

    def test_all_eleven_operational_requirements_have_authority_offerings(self) -> None:
        document = json.loads(
            (METADATA / "evidence-offerings.json").read_text(encoding="utf-8")
        )
        authority_offerings = [
            offering
            for offering in document["offerings"]
            if offering["access"]["kind"] == "evidence-verification-api"
        ]

        self.assertEqual(len(authority_offerings), 11)
        self.assertEqual(
            {offering["access"]["source_type"] for offering in authority_offerings},
            {"immutable extract", "Relay lookup"},
        )
        for offering in authority_offerings:
            with self.subTest(offering=offering["id"]):
                access = offering["access"]
                self.assertTrue(access["endpoint_url"].endswith("/v1/evidence"))
                self.assertTrue(
                    access["discovery_url"].endswith("/v1/evidence-definitions")
                )

    def test_offering_purposes_match_authority_requirements(self) -> None:
        document = json.loads(
            (METADATA / "evidence-offerings.json").read_text(encoding="utf-8")
        )
        offerings = {offering["id"]: offering for offering in document["offerings"]}

        self.assertEqual(
            offerings["sipf-pension-payment-v1-offering"]["purposes"],
            ["https://id.registrystack.org/solmara/purpose/pension-payment-review"],
        )
        self.assertEqual(
            offerings["sipf-survivor-benefit-v1-offering"]["purposes"],
            [
                "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination"
            ],
        )
        self.assertEqual(
            offerings["nagdi-voucher-v1-offering"]["purposes"],
            ["https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"],
        )
        self.assertEqual(
            offerings["nagdi-livestock-v1-offering"]["purposes"],
            ["https://id.registrystack.org/solmara/purpose/livestock-movement-control"],
        )

    def test_cra_offerings_publish_only_the_supported_uin_lookup(self) -> None:
        for offering_id in (
            "cra-child-benefit-v1-offering",
            "cra-pension-death-v1-offering",
            "cra-citizen-record-v1-offering",
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

        self.assertIn('"values": {"uin": "2300118698"}', request)
        self.assertNotIn('"values": {"uin": "2300109568"}', request)


if __name__ == "__main__":
    unittest.main()
