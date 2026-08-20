from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "compose.coolify.provision.yaml"
# Each ministry runs its own signer application so that no Coolify application
# environment holds another ministry's private issuer key. Compose scopes a key
# to its container; only splitting the application scopes it to its owner.
SIGNER_GROUPS = {
    "mint": ("mint",),
    "interior": ("cra", "nia"),
    "social-development": ("sro", "mosd"),
    "labour-pensions": ("sipf",),
    "agriculture": ("nagdi",),
}
SIGNER_COMPOSES = {
    group: ROOT / f"compose.coolify.signers.{group}.yaml" for group in SIGNER_GROUPS
}
RUNTIME_COMPOSES = (
    ROOT / "compose.coolify.yaml",
    ROOT / "compose.coolify.interior.yaml",
    ROOT / "compose.coolify.social-development.yaml",
    ROOT / "compose.coolify.labour-pensions.yaml",
    ROOT / "compose.coolify.agriculture.yaml",
)
PROVIDERS = ("mint", "cra", "nia", "sro", "mosd", "sipf", "nagdi")
RELAYS = ("cra", "nia", "mosd", "sipf", "nagdi")
EXTRACT_PROVIDERS = ("cra", "nia", "sro")
# Coolify rewrites every named volume reference to `{app_uuid}_{key}` and never
# consults `external: true`, so one named volume cannot be shared between the
# provisioning application and its consumers. Shared authority state is
# addressed by absolute host path instead, laid out as `<root>/<cell>/<role>`.
STATE_ROOT = "/data/solmara-authority-cells"
CELL_ROLES = {
    "mint": {"runtime", "secrets", "transit"},
    **{f"{authority}-relay": {"runtime", "source"} for authority in RELAYS},
    **{
        f"{provider}-evidence": {"runtime", "secrets", "transit"}
        | ({"extracts"} if provider in EXTRACT_PROVIDERS else set())
        for provider in PROVIDERS[1:]
    },
}
SHARED_PATHS = {
    f"{STATE_ROOT}/{cell}/{role}" for cell, roles in CELL_ROLES.items() for role in roles
}
TRANSIT_PATHS = {
    f"{STATE_ROOT}/{cell}/transit"
    for cell, roles in CELL_ROLES.items()
    if "transit" in roles
}
EVIDENCE_CLIENTS = {
    "cra": {"cra-pension-evidence", "cra-citizen-evidence"},
    "nia": set(),
    "sro": set(),
    "mosd": {"mosd-child-benefit-evidence"},
    "sipf": {"sipf-pension-evidence", "sipf-survivor-evidence"},
    "nagdi": {"nagdi-voucher-evidence", "nagdi-livestock-evidence"},
}
MINT_CLIENTS = {
    *(client for clients in EVIDENCE_CLIENTS.values() for client in clients),
    "nia-esignet",
}
TARGET_PROVISIONERS = {
    *(f"{authority}-relay-provisioner" for authority in RELAYS),
    *(f"{provider}-evidence-provisioner" for provider in PROVIDERS[1:]),
    "mint-provisioner",
}
INTERPOLATION = re.compile(r"^\$\{([A-Z][A-Z0-9_]*):\?[^}]+\}$")
FIXTURE_IMAGE = "ghcr.io/registrystack/solmara-test@sha256:" + "a" * 64
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


def service_mounts(service):
    """Yield (source, target, mode) per mount, with mode None when unset."""
    for mount in service.get("volumes", []):
        parts = mount.split(":")
        if len(parts) == 2:
            yield parts[0], parts[1], None
        elif len(parts) == 3:
            yield parts[0], parts[1], parts[2]
        else:
            raise AssertionError(f"unparsable mount {mount!r}")


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
        cls.signers = {
            group: yaml.safe_load(path.read_text(encoding="utf-8"))
            for group, path in SIGNER_COMPOSES.items()
        }
        cls.signer_services = {}
        for group, compose in cls.signers.items():
            for name, service in compose["services"].items():
                assert name not in cls.signer_services, (group, name)
                cls.signer_services[name] = service
        cls.runtime = {
            path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in RUNTIME_COMPOSES
        }

    def test_provisioning_application_writes_every_shared_authority_path(self) -> None:
        self.assertEqual(len(SHARED_PATHS), 34)
        self.assertNotIn("volumes", self.provision)
        written: set[str] = set()
        for name, service in self.provision["services"].items():
            for source, _, mode in service_mounts(service):
                self.assertIn(source, SHARED_PATHS, (name, source))
                self.assertIsNone(mode, (name, source))
                written.add(source)
        # The signer application creates and owns the Transit sockets; this
        # application writes every other shared path.
        self.assertEqual(written, SHARED_PATHS - TRANSIT_PATHS)

    def test_no_application_declares_a_shared_named_volume(self) -> None:
        for path in (PROVISION, *SIGNER_COMPOSES.values(), *RUNTIME_COMPOSES):
            compose = yaml.safe_load(path.read_text(encoding="utf-8"))
            for key, value in (compose.get("volumes") or {}).items():
                name = (value or {}).get("name", "")
                self.assertFalse(
                    name.startswith("solmara-authority-cells-"),
                    (path.name, key, name),
                )

    def test_provisioning_application_contains_only_target_provisioners(self) -> None:
        services = self.provision["services"]
        self.assertEqual(set(services), {*TARGET_PROVISIONERS, "provisioning-ready"})
        self.assertNotIn("SOLMARA_TRANSIT_SIGNER_IMAGE", PROVISION.read_text())
        self.assertNotIn("--private-jwk", PROVISION.read_text())
        private_signing_secrets = {
            "mint-signing-jwk",
            *(f"{provider}-evidence-signing-jwk" for provider in PROVIDERS[1:]),
        }
        self.assertTrue(private_signing_secrets.isdisjoint(self.provision["secrets"]))

    def test_runtime_applications_attach_shared_paths_read_only(self) -> None:
        attached: set[str] = set()
        for filename, compose in self.runtime.items():
            declared = compose.get("volumes") or {}
            for name, service in compose["services"].items():
                for source, _, mode in service_mounts(service):
                    if source.startswith("/"):
                        self.assertIn(source, SHARED_PATHS, (filename, name, source))
                        self.assertEqual(mode, "ro", (filename, name, source))
                        attached.add(source)
                        continue
                    # Every other mount is an app-local writable audit volume
                    # that no other application can reach.
                    self.assertIsNone(declared[source], (filename, source))
                    self.assertTrue(source.endswith("-audit"), (filename, source))
        self.assertEqual(attached, SHARED_PATHS)

    def test_private_signing_keys_are_mounted_only_into_matching_signers(self) -> None:
        services = self.signer_services
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
        services = self.signer_services
        for provider in PROVIDERS:
            prefix = "mint" if provider == "mint" else f"{provider}-evidence"
            signer = services[f"{provider}-signer"]
            secrets = {item["target"]: item["source"] for item in signer["secrets"]}
            self.assertEqual(len(secrets), 2)
            self.assertEqual(
                secrets["/tmp/solmara-signing.jwk"], f"{prefix}-signing-jwk"
            )
            self.assertEqual(
                secrets["/tmp/solmara-signing-public.jwk"],
                f"{prefix}-signing-public-jwk",
            )
            self.assertEqual(
                signer["command"][0:4],
                [
                    "--private-jwk",
                    "/tmp/solmara-signing.jwk",
                    "--public-jwk",
                    "/tmp/solmara-signing-public.jwk",
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
            self.assertIn(f"/tmp/solmara-provisioning/{client}-public.jwk", targets)
        self.assertIn(
            "/tmp/solmara-provisioning/solmara-demo-client-public.jwk", targets
        )

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

    def test_provisioner_secret_inventory_is_exact(self) -> None:
        consumed_sources: set[str] = set()
        for provider in PROVIDERS[1:]:
            service = self.provision["services"][f"{provider}-evidence-provisioner"]
            targets = {
                Path(item["target"]).name: item["source"] for item in service["secrets"]
            }
            expected = {
                "signing-public.jwk": f"{provider}-evidence-signing-public-jwk",
                "audit-hmac-key": f"{provider}-evidence-audit-hmac-key",
                "subject-binding-hmac-key": (
                    f"{provider}-evidence-subject-binding-hmac-key"
                ),
                **{
                    f"{client}-client-key": f"{client}-client-key"
                    for client in EVIDENCE_CLIENTS[provider]
                },
            }
            self.assertEqual(targets, expected)
            consumed_sources.update(targets.values())

        mint = self.provision["services"]["mint-provisioner"]
        mint_targets = {
            Path(item["target"]).name: item["source"] for item in mint["secrets"]
        }
        expected_mint = {
            "signing-public.jwk": "mint-signing-public-jwk",
            "audit-hmac-key": "mint-audit-hmac-key",
            "solmara-demo-client-public.jwk": "solmara-demo-client-public-jwk",
            **{
                f"{client}-public.jwk": f"{client}-client-public-jwk"
                for client in MINT_CLIENTS
            },
        }
        self.assertEqual(mint_targets, expected_mint)
        consumed_sources.update(mint_targets.values())
        self.assertEqual(set(self.provision["secrets"]), consumed_sources)

    def test_relay_provisioners_receive_no_secret(self) -> None:
        services = self.provision["services"]
        for authority in RELAYS:
            relay = services[f"{authority}-relay-provisioner"]
            self.assertNotIn("secrets", relay)
            self.assertNotIn("--secrets", relay["command"])

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
                self.assertNotIn("tmpfs", service)
                self.assertEqual(
                    service["command"][service["command"].index("--secrets") + 1],
                    "/tmp/solmara-provisioning",
                )
                for secret in service["secrets"]:
                    self.assertTrue(
                        secret["target"].startswith("/tmp/solmara-provisioning/")
                    )
                    self.assertEqual(secret["uid"], "0")
                    self.assertEqual(secret["gid"], "0")
                    self.assertEqual(secret["mode"], 0o400)
            else:
                self.assertTrue(service["read_only"])
                self.assertEqual(service["tmpfs"], "/tmp")

    def test_provisioning_readiness_requires_all_targets_to_complete(self) -> None:
        readiness = self.provision["services"]["provisioning-ready"]
        self.assertEqual(
            readiness["depends_on"],
            {
                target: {"condition": "service_completed_successfully"}
                for target in TARGET_PROVISIONERS
            },
        )
        self.assertEqual(readiness["command"], ["ready"])
        self.assertEqual(readiness["user"], "65532:65532")
        self.assertEqual(readiness["network_mode"], "none")
        self.assertTrue(readiness["read_only"])
        self.assertEqual(readiness["tmpfs"], "/tmp")
        self.assertEqual(readiness["cap_drop"], ["ALL"])
        self.assertNotIn("cap_add", readiness)
        self.assertNotIn("secrets", readiness)
        self.assertNotIn("volumes", readiness)

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

    def test_evidence_provisioners_bind_all_interfaces_on_addressed_runtimes(
        self,
    ) -> None:
        runtime_services = {
            "cra": self.runtime["compose.coolify.interior.yaml"]["services"][
                "cra-evidence"
            ],
            "nia": self.runtime["compose.coolify.interior.yaml"]["services"][
                "nia-evidence"
            ],
            "sro": self.runtime["compose.coolify.social-development.yaml"]["services"][
                "sro-evidence"
            ],
            "mosd": self.runtime["compose.coolify.social-development.yaml"]["services"][
                "mosd-programme-evidence"
            ],
            "sipf": self.runtime["compose.coolify.labour-pensions.yaml"]["services"][
                "sipf-evidence"
            ],
            "nagdi": self.runtime["compose.coolify.agriculture.yaml"]["services"][
                "nagdi-evidence"
            ],
        }
        for authority, runtime in runtime_services.items():
            provisioner = self.provision["services"][
                f"{authority}-evidence-provisioner"
            ]
            command = provisioner["command"]
            self.assertEqual(command[command.index("--bind-host") + 1], "0.0.0.0")
            self.assertIn("ipv4_address", runtime["networks"]["runtime"], authority)

    def test_each_signer_and_transit_initializer_mount_only_its_matching_volume(
        self,
    ) -> None:
        services = self.signer_services
        for provider in PROVIDERS:
            cell = "mint" if provider == "mint" else f"{provider}-evidence"
            path = f"{STATE_ROOT}/{cell}/transit"
            self.assertIn(path, TRANSIT_PATHS)
            self.assertEqual(
                services[f"{provider}-transit-init"]["volumes"], [f"{path}:/transit"]
            )
            signer = services[f"{provider}-signer"]
            self.assertEqual(signer["volumes"], [f"{path}:/transit"])
            self.assertEqual(
                signer["depends_on"],
                {
                    f"{provider}-transit-init": {
                        "condition": "service_completed_successfully"
                    }
                },
            )

    def test_signer_applications_have_exact_services_and_secrets(self) -> None:
        for group, providers in SIGNER_GROUPS.items():
            with self.subTest(group=group):
                compose = self.signers[group]
                expected_services = {
                    *(f"{provider}-transit-init" for provider in providers),
                    *(f"{provider}-signer" for provider in providers),
                    f"{group}-signers-ready",
                }
                self.assertEqual(set(compose["services"]), expected_services)

                expected_secrets: set[str] = set()
                for provider in providers:
                    prefix = "mint" if provider == "mint" else f"{provider}-evidence"
                    expected_secrets.update(
                        {f"{prefix}-signing-jwk", f"{prefix}-signing-public-jwk"}
                    )
                self.assertEqual(set(compose["secrets"]), expected_secrets)
                self.assertNotIn("volumes", compose)

                readiness = compose["services"][f"{group}-signers-ready"]
                self.assertEqual(
                    readiness["depends_on"],
                    {
                        f"{provider}-signer": {"condition": "service_healthy"}
                        for provider in providers
                    },
                )
                self.assertEqual(readiness["network_mode"], "none")
                self.assertTrue(readiness["read_only"])
                self.assertEqual(readiness["cap_drop"], ["ALL"])

                self.assertEqual(
                    {service["image"] for service in compose["services"].values()},
                    {
                        "${SOLMARA_TRANSIT_SIGNER_IMAGE:?set the digest-pinned Solmara Transit signer image}"
                    },
                )

    def test_signer_applications_partition_the_private_key_boundary(self) -> None:
        self.assertEqual(
            {provider for providers in SIGNER_GROUPS.values() for provider in providers},
            set(PROVIDERS),
        )
        seen_secrets: set[str] = set()
        seen_paths: set[str] = set()
        for group, providers in SIGNER_GROUPS.items():
            compose = self.signers[group]
            secrets = set(compose["secrets"])
            self.assertTrue(seen_secrets.isdisjoint(secrets), group)
            seen_secrets |= secrets

            owned = {
                f"{STATE_ROOT}/{'mint' if p == 'mint' else f'{p}-evidence'}/transit"
                for p in providers
            }
            mounted = {
                source
                for service in compose["services"].values()
                for source, _, _ in service_mounts(service)
            }
            # An application may reach its own cells' Transit sockets and
            # nothing else under the shared authority state root.
            self.assertEqual(mounted, owned, group)
            self.assertTrue(seen_paths.isdisjoint(mounted), group)
            seen_paths |= mounted
        self.assertEqual(seen_paths, TRANSIT_PATHS)

    def test_rendered_operator_applications_fit_coolify_payload_limit(self) -> None:
        for path, compose in (
            (PROVISION, self.provision),
            *((SIGNER_COMPOSES[group], self.signers[group]) for group in SIGNER_GROUPS),
        ):
            with self.subTest(compose=path.name):
                rendered = yaml.safe_dump(
                    fixture_render(compose), sort_keys=False
                ).encode("utf-8")
                self.assertLess(len(rendered), 65_536)

    def test_signer_application_preserves_process_confinement(self) -> None:
        services = self.signer_services
        for provider in PROVIDERS:
            initializer = services[f"{provider}-transit-init"]
            self.assertEqual(initializer["user"], "0:0")
            self.assertEqual(initializer["network_mode"], "none")
            self.assertTrue(initializer["read_only"])
            self.assertEqual(initializer["cap_drop"], ["ALL"])
            self.assertEqual(set(initializer["cap_add"]), {"CHOWN", "FOWNER"})
            self.assertEqual(initializer["security_opt"], ["no-new-privileges:true"])

            signer = services[f"{provider}-signer"]
            self.assertEqual(signer["user"], "65532:65532")
            self.assertEqual(signer["network_mode"], "none")
            self.assertFalse(signer["read_only"])
            self.assertNotIn("tmpfs", signer)
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
                    "mint-readiness",
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

    def test_core_deployment_waits_for_private_mint_health(self) -> None:
        core = self.runtime["compose.coolify.yaml"]["services"]
        readiness = core["mint-readiness"]
        self.assertEqual(
            readiness["depends_on"], {"mint": {"condition": "service_started"}}
        )
        self.assertEqual(readiness["networks"], ["runtime"])
        self.assertEqual(readiness["cap_drop"], ["ALL"])
        self.assertTrue(readiness["read_only"])
        self.assertNotIn("secrets", readiness)
        self.assertIn("172.29.1.20:8081/health", readiness["command"][0])
        self.assertEqual(
            core["scenario-runner"]["depends_on"],
            {"mint-readiness": {"condition": "service_completed_successfully"}},
        )


if __name__ == "__main__":
    unittest.main()
