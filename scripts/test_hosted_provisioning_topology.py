from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "compose.coolify.provision.yaml"
SIGNERS = ROOT / "compose.coolify.signers.yaml"
RUNTIME_COMPOSES = (
    ROOT / "compose.coolify.yaml",
    ROOT / "compose.coolify.interior.yaml",
    ROOT / "compose.coolify.social-development.yaml",
    ROOT / "compose.coolify.labour-pensions.yaml",
    ROOT / "compose.coolify.agriculture.yaml",
)
PROVIDERS = ("mint", "cra", "nia", "sro", "mosd", "sipf", "nagdi")
RELAYS = ("cra", "nia", "mosd", "sipf", "nagdi")
INTERPOLATION = re.compile(r"^\$\{([A-Z][A-Z0-9_]*):\?[^}]+\}$")
FIXTURE_IMAGE = (
    "ghcr.io/registrystack/solmara-test@sha256:"
    + "a" * 64
)
FIXTURE_PRIVATE_JWK_MEMBERS = {
    "kty": "EC",
    "crv": "P-384",
    "x": "A" * 64,
    "y": "B" * 64,
    "d": "C" * 64,
    "kid": "solmara-test",
    "alg": "ES384",
}
FIXTURE_PRIVATE_JWK = json.dumps(FIXTURE_PRIVATE_JWK_MEMBERS, separators=(",", ":"))
FIXTURE_PUBLIC_JWK = json.dumps(
    {key: value for key, value in FIXTURE_PRIVATE_JWK_MEMBERS.items() if key != "d"},
    separators=(",", ":"),
)
MINT_ORIGIN = "https://mint-authority-cells.solmara.registrystack.org"
RELAY_ORIGINS = {
    "cra": "https://cra-relay-authority-cells.solmara.registrystack.org",
    "mosd": "https://mosd-programme-relay-authority-cells.solmara.registrystack.org",
    "sipf": "https://sipf-relay-authority-cells.solmara.registrystack.org",
    "nagdi": "https://nagdi-relay-authority-cells.solmara.registrystack.org",
}


def fixture_render(value):
    if isinstance(value, dict):
        return {key: fixture_render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [fixture_render(item) for item in value]
    if not isinstance(value, str):
        return value
    match = INTERPOLATION.fullmatch(value)
    if match is None:
        return value
    variable = match.group(1)
    if variable.endswith("_IMAGE"):
        return FIXTURE_IMAGE
    if variable.endswith("_PUBLIC_JWK"):
        return FIXTURE_PUBLIC_JWK
    if variable.endswith("_PRIVATE_JWK") or variable.endswith("_SIGNING_JWK"):
        return FIXTURE_PRIVATE_JWK
    return "fixture-value"


class HostedProvisioningTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provision = yaml.safe_load(PROVISION.read_text(encoding="utf-8"))
        cls.signers = yaml.safe_load(SIGNERS.read_text(encoding="utf-8"))
        cls.runtime = {
            path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in RUNTIME_COMPOSES
        }

    def test_provisioning_application_owns_exactly_34_active_volumes(self) -> None:
        volumes = self.provision["volumes"]
        self.assertEqual(len(volumes), 34)
        self.assertTrue(
            all(not value.get("external", False) for value in volumes.values())
        )
        self.assertTrue(
            all(
                value["name"].startswith("solmara-authority-cells-")
                for value in volumes.values()
            )
        )

    def test_provisioning_application_contains_only_target_provisioners(self) -> None:
        services = self.provision["services"]
        self.assertEqual(len(services), 12)
        self.assertTrue(all(name.endswith("-provisioner") for name in services))
        self.assertNotIn("SOLMARA_TRANSIT_SIGNER_IMAGE", PROVISION.read_text())
        self.assertNotIn("--private-jwk", PROVISION.read_text())
        private_signing_secrets = {
            "mint-signing-jwk",
            *(f"{provider}-evidence-signing-jwk" for provider in PROVIDERS[1:]),
        }
        self.assertTrue(private_signing_secrets.isdisjoint(self.provision["secrets"]))

    def test_runtime_applications_attach_active_volumes_read_only_by_fixed_name(
        self,
    ) -> None:
        provisioned = {value["name"] for value in self.provision["volumes"].values()}
        attached: set[str] = set()
        for compose in self.runtime.values():
            for key, value in compose.get("volumes", {}).items():
                if not value or not value.get("external"):
                    continue
                name = value.get("name", "")
                if name in provisioned:
                    attached.add(name)
                    for service in compose["services"].values():
                        for mount in service.get("volumes", []):
                            if isinstance(mount, str) and mount.startswith(f"{key}:"):
                                self.assertTrue(mount.endswith(":ro"), mount)
        self.assertEqual(attached, provisioned)

    def test_private_signing_keys_are_mounted_only_into_matching_signers(self) -> None:
        services = self.signers["services"]
        for provider in PROVIDERS:
            secret = (
                "mint-signing-jwk"
                if provider == "mint"
                else f"{provider}-evidence-signing-jwk"
            )
            consumers = {
                service_name
                for service_name, service in services.items()
                if any(item["source"] == secret for item in service.get("secrets", []))
            }
            self.assertEqual(consumers, {f"{provider}-signer"})
        for name, service in self.provision["services"].items():
            if name.endswith("provisioner"):
                targets = {item["target"] for item in service.get("secrets", [])}
                self.assertNotIn("solmara-provisioning/signing.jwk", targets)

    def test_each_signer_requires_its_matching_public_projection(self) -> None:
        services = self.signers["services"]
        for provider in PROVIDERS:
            prefix = "mint" if provider == "mint" else f"{provider}-evidence"
            signer = services[f"{provider}-signer"]
            secrets = {item["target"]: item["source"] for item in signer["secrets"]}
            self.assertEqual(len(secrets), 2)
            self.assertEqual(secrets["signing.jwk"], f"{prefix}-signing-jwk")
            self.assertEqual(
                secrets["signing-public.jwk"], f"{prefix}-signing-public-jwk"
            )
            self.assertEqual(
                signer["command"][0:4],
                [
                    "--private-jwk",
                    "/run/secrets/signing.jwk",
                    "--public-jwk",
                    "/run/secrets/signing-public.jwk",
                ],
            )

    def test_mint_client_public_keys_use_provisioner_contract_names(self) -> None:
        mint = self.provision["services"]["mint-provisioner"]
        targets = {secret["target"] for secret in mint["secrets"]}
        clients = (
            "cra-pension-evidence",
            "cra-citizen-evidence",
            "mosd-child-benefit-evidence",
            "sipf-pension-evidence",
            "sipf-survivor-evidence",
            "nagdi-voucher-evidence",
            "nagdi-livestock-evidence",
            "nia-esignet",
        )
        for client in clients:
            self.assertIn(f"solmara-provisioning/{client}-public.jwk", targets)
        self.assertIn("solmara-provisioning/solmara-demo-client-public.jwk", targets)

    def test_each_evidence_provisioner_receives_only_its_public_signing_key(
        self,
    ) -> None:
        services = self.provision["services"]
        for provider in PROVIDERS[1:]:
            provisioner = services[f"{provider}-evidence-provisioner"]
            sources = {item["source"] for item in provisioner["secrets"]}
            self.assertIn(f"{provider}-evidence-signing-public-jwk", sources)
            self.assertFalse(any(source.endswith("-signing-jwk") for source in sources))
            foreign_prefixes = {
                f"{other}-evidence-" for other in PROVIDERS[1:] if other != provider
            }
            self.assertFalse(
                any(source.startswith(tuple(foreign_prefixes)) for source in sources),
                (provider, sources),
            )

    def test_relay_provisioners_receive_no_secret(self) -> None:
        services = self.provision["services"]
        for authority in RELAYS:
            self.assertNotIn("secrets", services[f"{authority}-relay-provisioner"])

    def test_provisioners_only_elevate_for_authority_volume_initialization(
        self,
    ) -> None:
        for name, service in self.provision["services"].items():
            if not name.endswith("-provisioner"):
                continue
            self.assertEqual(service["user"], "0:0")
            self.assertEqual(service["network_mode"], "none")
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertEqual(
                set(service["cap_add"]), {"CHOWN", "DAC_OVERRIDE", "FOWNER"}
            )
            self.assertEqual(service["security_opt"], ["no-new-privileges:true"])
            if service.get("secrets"):
                self.assertFalse(service["read_only"])
                self.assertEqual(set(service["tmpfs"]), {"/tmp", "/run/secrets"})
            else:
                self.assertTrue(service["read_only"])
                self.assertEqual(service["tmpfs"], ["/tmp"])

    def test_provisioners_receive_closed_permanent_dependency_origins(self) -> None:
        services = self.provision["services"]
        for name, service in services.items():
            if not name.endswith("provisioner"):
                continue
            command = service["command"]
            self.assertEqual(command[command.index("--mint-origin") + 1], MINT_ORIGIN)
            if name.endswith("-evidence-provisioner"):
                provider = name.removesuffix("-evidence-provisioner")
                if provider in RELAY_ORIGINS:
                    self.assertEqual(
                        command[command.index("--relay-origin") + 1],
                        RELAY_ORIGINS[provider],
                    )
                else:
                    self.assertNotIn("--relay-origin", command)
            else:
                self.assertNotIn("--relay-origin", command)

    def test_each_signer_and_transit_initializer_mount_only_its_matching_volume(
        self,
    ) -> None:
        services = self.signers["services"]
        for provider in PROVIDERS:
            volume = (
                "mint-transit" if provider == "mint" else f"{provider}-evidence-transit"
            )
            self.assertEqual(
                services[f"{provider}-transit-init"]["volumes"], [f"{volume}:/transit"]
            )
            signer = services[f"{provider}-signer"]
            self.assertEqual(signer["volumes"], [f"{volume}:/transit"])
            self.assertEqual(
                signer["depends_on"],
                {
                    f"{provider}-transit-init": {
                        "condition": "service_completed_successfully"
                    }
                },
            )

    def test_signer_application_has_exact_services_secrets_and_external_volumes(
        self,
    ) -> None:
        expected_services = {
            *(f"{provider}-transit-init" for provider in PROVIDERS),
            *(f"{provider}-signer" for provider in PROVIDERS),
        }
        self.assertEqual(set(self.signers["services"]), expected_services)

        expected_secrets: set[str] = set()
        expected_volumes: set[str] = set()
        for provider in PROVIDERS:
            prefix = "mint" if provider == "mint" else f"{provider}-evidence"
            expected_secrets.update(
                {f"{prefix}-signing-jwk", f"{prefix}-signing-public-jwk"}
            )
            expected_volumes.add(f"{prefix}-transit")
        self.assertEqual(set(self.signers["secrets"]), expected_secrets)
        self.assertEqual(set(self.signers["volumes"]), expected_volumes)
        self.assertTrue(
            all(
                value == {
                    "external": True,
                    "name": f"solmara-authority-cells-{key}",
                }
                for key, value in self.signers["volumes"].items()
            )
        )

        self.assertEqual(
            {service["image"] for service in self.signers["services"].values()},
            {
                "${SOLMARA_TRANSIT_SIGNER_IMAGE:?set the digest-pinned Solmara Transit signer image}"
            },
        )

    def test_rendered_operator_applications_fit_coolify_payload_limit(self) -> None:
        for path, compose in (
            (PROVISION, self.provision),
            (SIGNERS, self.signers),
        ):
            with self.subTest(compose=path.name):
                rendered = yaml.safe_dump(
                    fixture_render(compose), sort_keys=False
                ).encode("utf-8")
                self.assertLess(len(rendered), 65_536)

    def test_signer_application_preserves_process_confinement(self) -> None:
        services = self.signers["services"]
        for provider in PROVIDERS:
            initializer = services[f"{provider}-transit-init"]
            self.assertEqual(initializer["user"], "0:0")
            self.assertEqual(initializer["network_mode"], "none")
            self.assertTrue(initializer["read_only"])
            self.assertEqual(initializer["cap_drop"], ["ALL"])
            self.assertEqual(set(initializer["cap_add"]), {"CHOWN", "FOWNER"})
            self.assertEqual(
                initializer["security_opt"], ["no-new-privileges:true"]
            )

            signer = services[f"{provider}-signer"]
            self.assertEqual(signer["user"], "65532:65532")
            self.assertEqual(signer["network_mode"], "none")
            self.assertFalse(signer["read_only"])
            self.assertEqual(set(signer["tmpfs"]), {"/tmp", "/run/secrets"})
            self.assertEqual(signer["cap_drop"], ["ALL"])
            self.assertNotIn("cap_add", signer)
            self.assertEqual(signer["security_opt"], ["no-new-privileges:true"])
            self.assertEqual(signer["healthcheck"]["retries"], 30)

    def test_relay_runtime_secrets_are_authority_scoped(self) -> None:
        services = {}
        for compose in self.runtime.values():
            services.update(compose["services"])
        for authority in RELAYS:
            environment = services[f"{authority}-relay"]["environment"]
            expected = {
                "SOLMARA_RELAY_AUDIT_KEY": f"${{{authority.upper()}_RELAY_AUDIT_KEY:?required}}"
            }
            if authority in {"sipf", "nagdi"}:
                expected["SOLMARA_RELAY_CURSOR_KEY"] = (
                    f"${{{authority.upper()}_RELAY_CURSOR_KEY:?required}}"
                )
            self.assertEqual(environment, expected)

    def test_runtime_consumers_depend_on_app_local_audit_init(self) -> None:
        for compose in self.runtime.values():
            services = compose["services"]
            audit_init = services["audit-permissions"]
            self.assertEqual(audit_init["network_mode"], "none")
            self.assertEqual(audit_init["cap_add"], ["CHOWN", "FOWNER"])
            for name, service in services.items():
                if name in {
                    "audit-permissions",
                    "static-metadata",
                    "scenario-runner",
                    "child-benefit-federator",
                    "home",
                    "portal",
                }:
                    continue
                self.assertEqual(
                    service["depends_on"]["audit-permissions"],
                    {"condition": "service_completed_successfully"},
                    name,
                )


if __name__ == "__main__":
    unittest.main()
