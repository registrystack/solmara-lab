from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_smoke_live():
    spec = importlib.util.spec_from_file_location("smoke_live", ROOT / "scripts" / "smoke-live.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load smoke-live.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["smoke_live"] = module
    spec.loader.exec_module(module)
    return module


def load_compose_project_name():
    spec = importlib.util.spec_from_file_location(
        "compose_project_name", ROOT / "scripts" / "compose_project_name.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load compose_project_name.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["compose_project_name"] = module
    spec.loader.exec_module(module)
    return module


class QualityScriptTests(unittest.TestCase):
    def test_federation_key_rotation_is_isolated_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "federation.env"
            environment = {
                **os.environ,
                "CHILD_BENEFIT_PUBLIC_DOMAIN": "rotation.example.test",
            }
            command = [
                sys.executable,
                str(ROOT / "scripts" / "gen-secrets.py"),
                "--federation-output",
                str(output),
            ]
            generated = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

            values = {}
            for line in output.read_text(encoding="utf-8").splitlines():
                if not line or line.startswith("#"):
                    continue
                key, value = line.split("=", 1)
                values[key] = value.strip("'")
            self.assertEqual(values["CHILD_BENEFIT_PUBLIC_DOMAIN"], "rotation.example.test")
            jwks = {key: json.loads(value) for key, value in values.items() if key.endswith("_JWK")}
            self.assertEqual(len(jwks), 5)
            for jwk in jwks.values():
                self.assertIn(".rotation.example.test#", jwk["kid"])
                self.assertEqual(jwk["kty"], "OKP")
                self.assertIn("d", jwk)

            refused = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(refused.returncode, 1)
            self.assertIn("Refusing to overwrite", refused.stderr)

    def test_fiction_lint_passes_current_tree(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "check-fiction.sh")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_secret_lint_passes_current_tree(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "check-config-secrets.py")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hosted_configs_are_current(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "render-hosted-configs.py"), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_coolify_services_mount_durable_audit_state(self) -> None:
        expected_mounts = {
            "compose.coolify.interior.yaml": {
                "cra-civil-relay": [
                    "cra-civil-cache:/var/lib/registry-relay/cache",
                    "cra-civil-audit:/var/lib/registry-relay/audit",
                ],
                "nia-population-relay": [
                    "nia-population-cache:/var/lib/registry-relay/cache",
                    "nia-population-audit:/var/lib/registry-relay/audit",
                ],
                "civil-child-benefit-notary": [
                    "civil-child-benefit-notary-state:/var/lib/registry-notary/config-state",
                ],
                "nia-child-benefit-notary": [
                    "nia-child-benefit-notary-state:/var/lib/registry-notary/config-state",
                ],
            },
            "compose.coolify.social-development.yaml": {
                "sro-social-relay": [
                    "sro-social-cache:/var/lib/registry-relay/cache",
                    "sro-social-audit:/var/lib/registry-relay/audit",
                ],
                "programme-mis-relay": [
                    "programme-mis-cache:/var/lib/registry-relay/cache",
                    "programme-mis-audit:/var/lib/registry-relay/audit",
                ],
                "sro-child-benefit-notary": [
                    "sro-child-benefit-notary-state:/var/lib/registry-notary/config-state",
                ],
                "programme-child-benefit-notary": [
                    "programme-child-benefit-notary-state:/var/lib/registry-notary/config-state",
                ],
            },
            "compose.coolify.labour-pensions.yaml": {
                "sipf-pensions-relay": [
                    "sipf-pensions-cache:/var/lib/registry-relay/cache",
                    "sipf-pensions-audit:/var/lib/registry-relay/audit",
                ],
                "pension-notary": [
                    "pension-notary-state:/var/lib/registry-notary/config-state",
                ],
            },
            "compose.coolify.agriculture.yaml": {
                "nagdi-agriculture-relay": [
                    "nagdi-agriculture-cache:/var/lib/registry-relay/cache",
                    "nagdi-agriculture-audit:/var/lib/registry-relay/audit",
                ],
                "nagdi-notary": [
                    "nagdi-notary-state:/var/lib/registry-notary/config-state",
                ],
            },
            "compose.coolify.citizen-services.yaml": {
                "citizen-notary": [
                    "citizen-notary-state:/var/lib/registry-notary/config-state",
                ],
                "citizen-issuer-notary": [
                    "citizen-issuer-notary-state:/var/lib/registry-notary/config-state",
                ],
            },
        }

        for compose_name, service_mounts in expected_mounts.items():
            with self.subTest(compose=compose_name):
                compose = yaml.safe_load((ROOT / compose_name).read_text(encoding="utf-8"))
                declared_volumes = set((compose.get("volumes") or {}).keys())
                services = compose["services"]
                init_service = services["volume-permissions"]
                init_volume_names = {mount.split(":", 1)[0] for mount in init_service.get("volumes") or []}
                self.assertEqual(init_service.get("restart"), "unless-stopped")
                self.assertIn("healthcheck", init_service)

                for service_name, mounts in service_mounts.items():
                    service = services[service_name]
                    service_volumes = set(service.get("volumes") or [])
                    self.assertEqual(
                        (service.get("depends_on") or {}).get("volume-permissions", {}).get("condition"),
                        "service_healthy",
                    )
                    for mount in mounts:
                        with self.subTest(service=service_name, mount=mount):
                            volume_name = mount.split(":", 1)[0]
                            self.assertIn(mount, service_volumes)
                            self.assertIn(volume_name, declared_volumes)
                            self.assertIn(volume_name, init_volume_names)

    def test_hosted_child_benefit_topology_is_source_owned(self) -> None:
        core = yaml.safe_load((ROOT / "compose.coolify.yaml").read_text(encoding="utf-8"))
        core_services = core["services"]
        self.assertIn("child-benefit-federator", core_services)
        self.assertNotIn("child-benefit-notary", core_services)
        federator = core_services["child-benefit-federator"]
        federator_env = federator["environment"]
        self.assertEqual(federator_env["CHILD_BENEFIT_PUBLIC_DOMAIN"], "solmara.registrystack.org")
        self.assertEqual(
            federator["labels"]["solmara.lab.host"],
            "child-benefit-federator.solmara.registrystack.org",
        )

        expected = (
            (
                "compose.coolify.interior.yaml",
                "civil-child-benefit-notary",
                "cra-civil-relay",
                "child-benefit-civil.yaml",
                "civil",
                "CIVIL_CHILD_BENEFIT_NOTARY_URL",
                "CIVIL_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK",
            ),
            (
                "compose.coolify.interior.yaml",
                "nia-child-benefit-notary",
                "nia-population-relay",
                "child-benefit-population.yaml",
                "population",
                "NIA_CHILD_BENEFIT_NOTARY_URL",
                "NIA_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK",
            ),
            (
                "compose.coolify.social-development.yaml",
                "sro-child-benefit-notary",
                "sro-social-relay",
                "child-benefit-social.yaml",
                "social",
                "SRO_CHILD_BENEFIT_NOTARY_URL",
                "SRO_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK",
            ),
            (
                "compose.coolify.social-development.yaml",
                "programme-child-benefit-notary",
                "programme-mis-relay",
                "child-benefit-programme.yaml",
                "programme",
                "PROGRAMME_CHILD_BENEFIT_NOTARY_URL",
                "PROGRAMME_CHILD_BENEFIT_FEDERATION_RESPONSE_JWK",
            ),
        )
        for compose_name, service_id, relay_id, config_name, source_id, url_env, jwk_env in expected:
            with self.subTest(service=service_id):
                compose = yaml.safe_load((ROOT / compose_name).read_text(encoding="utf-8"))
                services = compose["services"]
                self.assertNotIn("child-benefit-notary", services)
                service = services[service_id]
                self.assertEqual(
                    (service.get("depends_on") or {}).get(relay_id, {}).get("condition"),
                    "service_healthy",
                )
                self.assertEqual(service["labels"]["solmara.lab.host"], f"{service_id}.solmara.registrystack.org")
                self.assertIn(jwk_env, service["environment"])

                public_url = f"https://{service_id}.solmara.registrystack.org"
                self.assertEqual(federator_env[url_env], public_url)
                config = yaml.safe_load((ROOT / "hosted" / "notaries" / config_name).read_text(encoding="utf-8"))
                self.assertEqual(config["instance"]["public_base_url"], public_url)
                self.assertEqual(set(config["evidence"]["source_connections"]), {source_id})
                self.assertEqual(config["federation"]["node_id"], f"did:web:{service_id}.solmara.registrystack.org")
                self.assertEqual(config["federation"]["issuer"], public_url)
                signing_key_id = config["federation"]["signing"]["signing_key"]
                signing_key = config["evidence"]["signing_keys"][signing_key_id]
                self.assertEqual(signing_key["private_jwk_env"], jwk_env)
                self.assertEqual(
                    signing_key["kid"],
                    f"did:web:{service_id}.solmara.registrystack.org#federation-key-1",
                )
                peers = config["federation"]["peers"]
                self.assertEqual(len(peers), 1)
                self.assertEqual(peers[0]["node_id"], "did:web:child-benefit-federator.solmara.registrystack.org")
                self.assertEqual(peers[0]["issuer"], "https://child-benefit-federator.solmara.registrystack.org")
                self.assertEqual(
                    peers[0]["jwks_uri"],
                    "https://child-benefit-federator.solmara.registrystack.org/.well-known/jwks.json",
                )
                self.assertNotIn("allow_insecure_localhost", peers[0])
                self.assertNotIn("allow_insecure_private_network", peers[0])

        self.assertFalse((ROOT / "hosted" / "notaries" / "child-benefit.yaml").exists())

    def test_story_preview_smoke_passes_current_tree(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "smoke-story-previews.py")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_live_smoke_extracts_claim_values(self) -> None:
        smoke_live = load_smoke_live()
        values = smoke_live.claim_values(
            {
                "results": [
                    {"claim_id": "population-record-active", "value": True},
                    {"claim_id": "not-already-enrolled", "satisfied": False},
                ]
            }
        )

        self.assertEqual(
            values,
            {"population-record-active": True, "not-already-enrolled": False},
        )

    def test_live_smoke_extracts_catalog_claim_ids(self) -> None:
        smoke_live = load_smoke_live()

        self.assertEqual(
            smoke_live.catalog_claim_ids({"data": [{"id": "person-is-deceased"}, {"id": "survivor-is-eligible"}]}),
            {"person-is-deceased", "survivor-is-eligible"},
        )

    def test_child_benefit_offerings_advertise_only_the_endpoint_purpose(self) -> None:
        expected_purposes = ["https://id.registrystack.org/solmara/purpose/child-benefit-review"]
        offering_ids = (
            "cra-birth-registration-offering",
            "nia-population-population-status-offering",
            "sro-social-household-poverty-offering",
            "mosd-programme-beneficiary-enrollment-offering",
        )

        for offering_id in offering_ids:
            with self.subTest(offering=offering_id):
                path = ROOT / "metadata" / "public" / "metadata" / "evidence-offerings" / f"{offering_id}.json"
                offering = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(offering["purposes"], expected_purposes)

    def test_child_benefit_federated_bundle_is_publicly_discoverable(self) -> None:
        catalog_path = ROOT / "metadata" / "public" / "metadata" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        services = {service["id"]: service for service in catalog["data_services"]}
        federator = services["child-benefit-federator-api"]

        self.assertEqual(
            federator["endpoint_url"],
            "https://child-benefit-federator.solmara.registrystack.org/v1/evaluations",
        )
        child_service = next(service for service in catalog["public_services"] if service["id"] == "child-benefit-review")
        self.assertIn("child-benefit-federator-api", child_service["data_services"])

        offering_path = (
            ROOT
            / "metadata"
            / "public"
            / "metadata"
            / "evidence-offerings"
            / "solmara.child-benefit.federated-predicate-bundle.json"
        )
        offering = json.loads(offering_path.read_text(encoding="utf-8"))
        self.assertEqual(
            offering["access"]["endpoint_url"],
            "https://child-benefit-federator.solmara.registrystack.org/v1/evaluations",
        )
        self.assertEqual(
            offering["access"]["media_type"],
            "application/vnd.solmara.federated-predicate-bundle+json",
        )
        self.assertEqual(
            offering["purposes"],
            ["https://id.registrystack.org/solmara/purpose/child-benefit-review"],
        )
        self.assertEqual(offering["public_services"], ["child-benefit-review"])

    def test_compose_project_name_is_stable_and_checkout_scoped(self) -> None:
        compose_names = load_compose_project_name()

        first = compose_names.compose_project_name(Path("/tmp/solmara-lab"))
        second = compose_names.compose_project_name(Path("/tmp/other/solmara-lab"))

        self.assertRegex(first, r"^solmara-lab-[0-9a-f]{10}$")
        self.assertNotEqual(first, second)

    def test_notary_bru_requests_match_configured_auth_and_disclosure(self) -> None:
        requests = [
            ROOT / "requests" / "registry-lab" / "20 - Child Benefit" / "01 - Collect source predicates.bru",
            ROOT / "requests" / "registry-lab" / "30 - Pension Survivor" / "01 - Evaluate pension stop.bru",
            ROOT / "requests" / "registry-lab" / "30 - Pension Survivor" / "02 - Survivor eligibility.bru",
            ROOT / "requests" / "registry-lab" / "40 - NAgDI Voucher" / "01 - Voucher eligibility.bru",
            ROOT / "requests" / "registry-lab" / "40 - NAgDI Voucher" / "02 - Livestock movement control.bru",
        ]

        for request_path in requests:
            with self.subTest(request=request_path.name):
                request = request_path.read_text()
                self.assertIn("x-api-key: {{", request)
                self.assertNotIn("Authorization: Bearer", request)
                self.assertIn('"disclosure": "predicate"', request)
                self.assertNotIn('"disclosure": "decision"', request)


if __name__ == "__main__":
    unittest.main()
