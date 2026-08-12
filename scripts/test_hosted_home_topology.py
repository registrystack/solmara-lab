from __future__ import annotations

import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).parents[1]
COMPOSE_PATH = ROOT / "compose.coolify.yaml"


class HostedHomeTopologyTests(unittest.TestCase):
    def test_home_build_context_exposes_only_public_generated_inputs(self) -> None:
        patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("!generator/output/**", patterns)
        self.assertIn("output/*", patterns)
        self.assertIn("!output/smoke", patterns)
        self.assertIn("output/smoke/*", patterns)
        self.assertIn("!output/smoke/.gitkeep", patterns)
        self.assertNotIn("!output/**", patterns)

    def test_home_uses_the_declared_public_topology_without_secrets(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        home = compose["services"]["home"]
        environment = home["environment"]

        expected_origins = {
            "PORTAL_URL": "https://portal.solmara.registrystack.org",
            "STATIC_METADATA_URL": "https://metadata.solmara.registrystack.org",
            "CRA_CIVIL_RELAY_URL": "https://cra-relay.solmara.registrystack.org",
            "NIA_POPULATION_RELAY_URL": "https://nia-relay.solmara.registrystack.org",
            "MOSD_PROGRAMME_RELAY_URL": "https://mosd-programme-relay.solmara.registrystack.org",
            "SIPF_PENSIONS_RELAY_URL": "https://sipf-relay.solmara.registrystack.org",
            "NAGDI_AGRICULTURE_RELAY_URL": "https://nagdi-relay.solmara.registrystack.org",
            "SOLMARA_CRA_EVIDENCE_URL": "https://cra-evidence.solmara.registrystack.org",
            "SOLMARA_NIA_EVIDENCE_URL": "https://nia-evidence.solmara.registrystack.org",
            "SOLMARA_SRO_EVIDENCE_URL": "https://sro-evidence.solmara.registrystack.org",
            "SOLMARA_MOSD_PROGRAMME_EVIDENCE_URL": "https://mosd-programme-evidence.solmara.registrystack.org",
            "SOLMARA_SIPF_EVIDENCE_URL": "https://sipf-evidence.solmara.registrystack.org",
            "SOLMARA_NAGDI_EVIDENCE_URL": "https://nagdi-evidence.solmara.registrystack.org",
            "MINT_URL": "https://mint.solmara.registrystack.org",
            "CHILD_BENEFIT_FEDERATOR_URL": "https://child-benefit.solmara.registrystack.org",
            "SCENARIO_RUNNER_URL": "https://scenarios.solmara.registrystack.org",
            "PORTAL_PROBE_URL": "https://portal.solmara.registrystack.org",
        }
        self.assertEqual(
            {key: environment.get(key) for key in expected_origins},
            expected_origins,
        )

        declared_hosts = set()
        for path in ROOT.glob("compose.coolify*.yaml"):
            hosted_compose = yaml.safe_load(path.read_text(encoding="utf-8"))
            for service in hosted_compose.get("services", {}).values():
                host = service.get("labels", {}).get("solmara.lab.host")
                if host:
                    declared_hosts.add(host)
        self.assertTrue(
            {urlparse(origin).hostname for origin in expected_origins.values()}
            <= declared_hosts
        )

        public_url_map = json.loads(environment["SOLMARA_PUBLIC_URL_MAP"])
        self.assertEqual(
            public_url_map,
            {
                "child-benefit-federator:8080": expected_origins["CHILD_BENEFIT_FEDERATOR_URL"],
                "deterministic-publisher:8080": expected_origins["STATIC_METADATA_URL"],
                "cra-evidence:8080": expected_origins["SOLMARA_CRA_EVIDENCE_URL"],
                "nia-evidence:8080": expected_origins["SOLMARA_NIA_EVIDENCE_URL"],
                "sro-evidence:8080": expected_origins["SOLMARA_SRO_EVIDENCE_URL"],
                "mosd-programme-evidence:8080": expected_origins["SOLMARA_MOSD_PROGRAMME_EVIDENCE_URL"],
                "sipf-evidence:8080": expected_origins["SOLMARA_SIPF_EVIDENCE_URL"],
                "nagdi-evidence:8080": expected_origins["SOLMARA_NAGDI_EVIDENCE_URL"],
                "mint:8081": expected_origins["MINT_URL"],
                "cra-relay:8080": expected_origins["CRA_CIVIL_RELAY_URL"],
                "nia-relay:8080": expected_origins["NIA_POPULATION_RELAY_URL"],
                "mosd-relay:8080": expected_origins["MOSD_PROGRAMME_RELAY_URL"],
                "sipf-relay:8080": expected_origins["SIPF_PENSIONS_RELAY_URL"],
                "nagdi-relay:8080": expected_origins["NAGDI_AGRICULTURE_RELAY_URL"],
                "static-metadata:8080": expected_origins["STATIC_METADATA_URL"],
                "scenario-runner:8080": expected_origins["SCENARIO_RUNNER_URL"],
                "portal:4000": expected_origins["PORTAL_PROBE_URL"],
            },
        )

        self.assertNotIn("secrets", home)
        self.assertNotIn("volumes", home)
        self.assertFalse(
            {"SOLMARA_EVIDENCE_CLIENT_KEY", "CHILD_BENEFIT_FEDERATOR_TOKEN"}
            & environment.keys()
        )


if __name__ == "__main__":
    unittest.main()
