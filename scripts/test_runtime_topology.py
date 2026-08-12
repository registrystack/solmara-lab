from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).with_name("check-runtime-topology.py")
SPEC = importlib.util.spec_from_file_location("runtime_topology", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimeTopologyTests(unittest.TestCase):
    def test_authority_runtime_uses_the_versioned_relayctl_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            runtime_script = scripts / "prepare-authority-runtime.sh"
            shutil.copy2(SCRIPT.with_name("prepare-authority-runtime.sh"), runtime_script)
            (root / "versions.env").write_text(
                "REGISTRY_RELAYCTL_IMAGE=example.invalid/relayctl:v0.20.1\n",
                encoding="utf-8",
            )
            publisher = scripts / "publish-relay-sources.sh"
            publisher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            publisher.chmod(0o755)

            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            fake_uv = fake_bin / "uv"
            fake_uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_uv.chmod(0o755)
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\n"
                "previous=\n"
                "for argument in \"$@\"; do\n"
                "  if [ \"$previous\" = --output ]; then\n"
                "    mkdir -p \"$argument\"\n"
                "    : > \"$argument/relay-package.json\"\n"
                "  fi\n"
                "  previous=$argument\n"
                "done\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)

            for authority in ("cra", "nia", "mosd", "sipf", "nagdi"):
                (root / "relays" / authority).mkdir(parents=True)

            docker_log = root / "docker.log"
            environment = os.environ.copy()
            environment.update(
                {
                    "DOCKER_LOG": str(docker_log),
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "REGISTRY_RELAYCTL_IMAGE": "wrong.invalid/relayctl:ambient",
                }
            )
            subprocess.run(
                [str(runtime_script)],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            invocations = docker_log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(invocations), 5)
        self.assertTrue(
            all("example.invalid/relayctl:v0.20.1" in line for line in invocations)
        )
        self.assertTrue(all("--platform linux/amd64" in line for line in invocations))
        self.assertTrue(all("wrong.invalid" not in line for line in invocations))

    def test_relay_publication_uses_pinned_linux_sqlite_runtime(self) -> None:
        script = SCRIPT.with_name("publish-relay-sources.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python:3.12-slim-trixie@sha256:", script)
        self.assertIn("--platform linux/amd64", script)
        self.assertIn("--network none", script)
        self.assertIn("--read-only", script)
        self.assertNotIn("uv run", script)

    def test_retired_surfaces_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "compose.yaml"
            path.write_text(
                "services:\n  old:\n    image: postgres:16\n", encoding="utf-8"
            )
            self.assertEqual(
                MODULE.failures([path]), ["compose.yaml:3: retired database"]
            )

    def test_current_active_topology_is_closed(self) -> None:
        self.assertEqual(MODULE.failures(), [])

    def test_local_relays_use_the_v2_runtime_filesystem_contract(self) -> None:
        compose_path = SCRIPT.parents[1] / "compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

        for authority in ("cra", "nia", "mosd", "sipf", "nagdi"):
            service = compose["services"][f"{authority}-relay"]
            self.assertEqual(
                service["command"],
                ["serve", "--runtime", f"/etc/relay/{authority}/runtime.yaml"],
            )
            volumes = set(service["volumes"])
            self.assertIn(
                f"./relays/{authority}/runtime.yaml:/etc/relay/{authority}/runtime.yaml:ro",
                volumes,
            )
            self.assertIn(
                f"./relays/{authority}/package:/etc/relay/{authority}/package:ro",
                volumes,
            )
            self.assertIn(
                f"{authority}-relay-source:/var/lib/relay/source:ro",
                volumes,
            )
            self.assertIn(
                f"{authority}-relay-audit:/var/lib/relay/audit",
                volumes,
            )
            self.assertEqual(
                service["depends_on"]["relay-audit-init"]["condition"],
                "service_completed_successfully",
            )
            self.assertEqual(
                service["depends_on"]["relay-issuer-readiness"]["condition"],
                "service_completed_successfully",
            )
            self.assertEqual(
                service["depends_on"][f"{authority}-source-publisher"]["condition"],
                "service_completed_successfully",
            )

            publisher = compose["services"][f"{authority}-source-publisher"]
            self.assertEqual(publisher["network_mode"], "none")
            self.assertEqual(publisher["user"], "0:0")
            self.assertTrue(publisher["read_only"])
            self.assertEqual(publisher["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", publisher["security_opt"])
            self.assertEqual(publisher["restart"], "no")
            self.assertEqual(publisher["command"], ["ensure-seeded"])
            publisher_volumes = set(publisher["volumes"])
            self.assertIn(
                f"./output/sqlite/relay/{authority}.sqlite:/seed/{authority}.sqlite:ro",
                publisher_volumes,
            )
            self.assertIn(
                f"{authority}-relay-source:/var/lib/relay/source",
                publisher_volumes,
            )
            for other in {"cra", "nia", "mosd", "sipf", "nagdi"} - {authority}:
                self.assertFalse(
                    any(
                        f"{other}-relay-source:" in volume
                        for volume in publisher_volumes
                    ),
                    (authority, other),
                )

        initializer = compose["services"]["relay-audit-init"]
        self.assertEqual(initializer["network_mode"], "none")
        self.assertEqual(initializer["user"], "0:0")
        self.assertEqual(initializer["cap_drop"], ["ALL"])
        self.assertEqual(set(initializer["cap_add"]), {"CHOWN", "FOWNER"})
        self.assertIn("no-new-privileges:true", initializer["security_opt"])
        audit_init = initializer["command"][2]
        self.assertIn("os.scandir(path)", audit_init)
        self.assertIn("stat.S_ISREG", audit_init)
        self.assertIn("metadata.st_nlink != 1", audit_init)
        self.assertIn("audit\\.jsonl\\.\\d{8}", audit_init)
        self.assertIn("follow_symlinks=False", audit_init)
        for authority in ("cra", "nia", "mosd", "sipf", "nagdi"):
            self.assertIn(
                f"{authority}-relay-audit:/audit/{authority}",
                initializer["volumes"],
            )

        issuer_readiness = compose["services"]["relay-issuer-readiness"]
        self.assertEqual(issuer_readiness["user"], "65532:65532")
        self.assertTrue(issuer_readiness["read_only"])
        self.assertEqual(issuer_readiness["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", issuer_readiness["security_opt"])
        self.assertEqual(issuer_readiness["restart"], "no")
        self.assertEqual(issuer_readiness["networks"], ["issuer-validation"])
        self.assertEqual(
            issuer_readiness["depends_on"],
            {
                "mint": {"condition": "service_started"},
                "evidence-gateway": {"condition": "service_started"},
            },
        )
        readiness_code = issuer_readiness["command"][2]
        self.assertIn("/.well-known/openid-configuration", readiness_code)
        self.assertIn("document.get('issuer') == issuer", readiness_code)
        self.assertIn("ssl.create_default_context", readiness_code)
        self.assertNotIn("token", readiness_code.lower())

    def test_authority_cells_have_fixed_private_addresses(self) -> None:
        compose_path = SCRIPT.parents[1] / "compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        expected = {
            "mint": "172.29.1.20",
            "cra-evidence": "172.29.1.21",
            "nia-evidence": "172.29.1.22",
            "sro-evidence": "172.29.1.23",
            "mosd-programme-evidence": "172.29.1.24",
            "sipf-evidence": "172.29.1.25",
            "nagdi-evidence": "172.29.1.26",
        }
        for service_name, address in expected.items():
            self.assertEqual(
                compose["services"][service_name]["networks"]["runtime"][
                    "ipv4_address"
                ],
                address,
            )

        caddy = (SCRIPT.parents[1] / "config/evidence/Caddyfile").read_text(
            encoding="utf-8"
        )
        evidence_routes = {
            "cra": "172.29.1.21",
            "nia": "172.29.1.22",
            "sro": "172.29.1.23",
            "mosd-programme": "172.29.1.24",
            "sipf": "172.29.1.25",
            "nagdi": "172.29.1.26",
        }
        for authority, address in evidence_routes.items():
            self.assertIn(f"handle_path /evidence/{authority}/*", caddy)
            self.assertIn(f"reverse_proxy {address}:8080", caddy)

    def test_local_oidc_issuer_uses_an_isolated_testnet_address(self) -> None:
        compose_path = SCRIPT.parents[1] / "compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

        issuer_network = compose["networks"]["issuer-validation"]
        self.assertTrue(issuer_network["internal"])
        self.assertEqual(
            issuer_network["ipam"]["config"],
            [{"subnet": "192.0.2.0/26", "ip_range": "192.0.2.0/27"}],
        )

        gateway_networks = compose["services"]["evidence-gateway"]["networks"]
        self.assertNotIn(
            "mint.solmara.registrystack.org",
            gateway_networks["runtime"]["aliases"],
        )
        self.assertEqual(
            gateway_networks["issuer-validation"],
            {
                "ipv4_address": "192.0.2.62",
                "aliases": ["mint.solmara.registrystack.org"],
            },
        )

        strict_oidc_consumers = {
            "cra-relay",
            "nia-relay",
            "mosd-relay",
            "sipf-relay",
            "nagdi-relay",
            "cra-evidence",
            "nia-evidence",
            "sro-evidence",
            "mosd-programme-evidence",
            "sipf-evidence",
            "nagdi-evidence",
        }
        for service_name in strict_oidc_consumers:
            self.assertIn(
                "issuer-validation",
                compose["services"][service_name]["networks"],
                service_name,
            )

    def test_local_root_signers_explicitly_accept_read_only_host_bind_owners(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())

        for provider in ("mint", "cra", "nia", "sro", "mosd-programme", "sipf", "nagdi"):
            signer = compose["services"][f"{provider}-signer"]
            self.assertEqual(signer["user"], "0:0")
            self.assertIn("--allow-root-bind-owner", signer["command"])
            self.assertTrue(any(volume.endswith("signing.jwk:ro") for volume in signer["volumes"]))

    def test_local_transit_signers_are_one_key_one_socket_sidecars(self) -> None:
        compose_path = SCRIPT.parents[1] / "compose.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        providers = {
            "mint": ("mint", "mint", "solmara-mint"),
            "cra": ("cra", "cra-evidence", "solmara-evidence-cra"),
            "nia": ("nia", "nia-evidence", "solmara-evidence-nia"),
            "sro": ("sro", "sro-evidence", "solmara-evidence-sro"),
            "mosd-programme": (
                "mosd-programme",
                "mosd-programme-evidence",
                "solmara-evidence-mosd-programme",
            ),
            "sipf": ("sipf", "sipf-evidence", "solmara-evidence-sipf"),
            "nagdi": ("nagdi", "nagdi-evidence", "solmara-evidence-nagdi"),
        }
        for signer_name, (provider, consumer_name, key_name) in providers.items():
            signer = compose["services"][f"{signer_name}-signer"]
            self.assertEqual(signer["network_mode"], "none")
            self.assertEqual(signer["user"], "0:0")
            self.assertEqual(signer["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", signer["security_opt"])
            key_name_index = signer["command"].index("--key-name")
            self.assertEqual(signer["command"][key_name_index + 1], key_name)
            signer_volumes = set(signer["volumes"])
            self.assertIn(
                f"./config/evidence/local/cells/{provider}/secrets/signing.jwk:/run/secrets/signing.jwk:ro",
                signer_volumes,
            )
            self.assertIn(f"{signer_name}-transit:/transit", signer_volumes)

            consumer = compose["services"][consumer_name]
            socket_destination = (
                "/run/registry-mint"
                if provider == "mint"
                else f"/run/registry-evidence/{provider}"
            )
            self.assertIn(
                f"{signer_name}-transit:{socket_destination}:ro",
                set(consumer["volumes"]),
            )
            self.assertEqual(
                consumer["depends_on"][f"{signer_name}-signer"]["condition"],
                "service_healthy",
            )

    def test_hosted_relays_keep_runtime_and_source_read_only(self) -> None:
        compose_paths = (
            SCRIPT.parents[1] / "compose.coolify.interior.yaml",
            SCRIPT.parents[1] / "compose.coolify.social-development.yaml",
            SCRIPT.parents[1] / "compose.coolify.labour-pensions.yaml",
            SCRIPT.parents[1] / "compose.coolify.agriculture.yaml",
        )
        services: dict[str, object] = {}
        for compose_path in compose_paths:
            compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
            services.update(compose["services"])

        for authority in ("cra", "nia", "mosd", "sipf", "nagdi"):
            service = services[f"{authority}-relay"]
            self.assertEqual(
                service["command"],
                ["serve", "--runtime", f"/etc/relay/{authority}/runtime.yaml"],
            )
            volumes = set(service["volumes"])
            self.assertIn(
                f"{authority}-relay-runtime:/etc/relay/{authority}:ro",
                volumes,
            )
            self.assertIn(
                f"{authority}-relay-source:/var/lib/relay/source:ro",
                volumes,
            )
            self.assertIn(
                f"{authority}-relay-audit:/var/lib/relay/audit",
                volumes,
            )

    def test_hosted_programme_services_receive_only_their_application_secrets(
        self,
    ) -> None:
        compose_path = SCRIPT.parents[1] / "compose.coolify.yaml"
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        services = compose["services"]
        secret_name = "solmara-demo-client-key"
        secret_target = "solmara-evidence-client.jwk"
        federator_token = "${CHILD_BENEFIT_FEDERATOR_TOKEN:?required}"

        self.assertEqual(
            compose["secrets"][secret_name],
            {"environment": "SOLMARA_DEMO_CLIENT_PRIVATE_JWK"},
        )
        for service_name in ("scenario-runner", "child-benefit-federator", "portal"):
            service = services[service_name]
            self.assertEqual(
                service["secrets"],
                [{"source": secret_name, "target": secret_target}],
                service_name,
            )
            self.assertEqual(
                service["environment"]["SOLMARA_EVIDENCE_CLIENT_ID"],
                "solmara-demo",
                service_name,
            )
            self.assertEqual(
                service["environment"]["SOLMARA_EVIDENCE_CLIENT_KEY"],
                f"/run/secrets/{secret_target}",
                service_name,
            )
            self.assertEqual(
                service["environment"]["CHILD_BENEFIT_FEDERATOR_TOKEN"],
                federator_token,
                service_name,
            )

        self.assertEqual(
            services["scenario-runner"]["environment"]["CHILD_BENEFIT_FEDERATOR_URL"],
            "https://child-benefit.solmara.registrystack.org",
        )
        self.assertEqual(
            services["portal"]["environment"]["CHILD_BENEFIT_FEDERATOR_URL"],
            "https://child-benefit.solmara.registrystack.org",
        )
        self.assertEqual(
            services["child-benefit-federator"]["environment"][
                "CHILD_BENEFIT_FEDERATOR_HOST"
            ],
            "0.0.0.0",
        )
        self.assertEqual(
            services["child-benefit-federator"]["environment"][
                "CHILD_BENEFIT_FEDERATOR_PORT"
            ],
            "8080",
        )

        for service_name in ("home", "static-metadata"):
            service = services[service_name]
            self.assertNotIn("secrets", service, service_name)
            environment = service.get("environment", {})
            self.assertNotIn("SOLMARA_EVIDENCE_CLIENT_KEY", environment, service_name)
            self.assertNotIn("CHILD_BENEFIT_FEDERATOR_TOKEN", environment, service_name)

    def test_hosted_esignet_overlay_wires_the_main_portal_with_a_separate_key(
        self,
    ) -> None:
        overlay_path = SCRIPT.parents[1] / "compose.coolify.esignet.yaml"
        overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
        services = overlay["services"]
        portal = services["portal"]["environment"]
        expected = {
            "PORTAL_AUTH_PROVIDER": "esignet",
            "PORTAL_SECURE_COOKIES": "true",
            "PORTAL_ESIGNET_CLIENT_ID": "${PORTAL_ESIGNET_CLIENT_ID:-solmara-portal}",
            "PORTAL_ESIGNET_CLIENT_KEY_ID": "${PORTAL_ESIGNET_CLIENT_KEY_ID:-solmara-portal-key-1}",
            "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64": "${PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64:?required}",
            "PORTAL_ESIGNET_ISSUER": "https://esignet.solmara.registrystack.org",
            "PORTAL_ESIGNET_AUTHORIZATION_ENDPOINT": "https://esignet-ui.solmara.registrystack.org/authorize",
            "PORTAL_ESIGNET_TOKEN_ENDPOINT": "https://esignet.solmara.registrystack.org/v1/esignet/oauth/v2/token",
            "PORTAL_ESIGNET_CLIENT_ASSERTION_AUDIENCE": "https://esignet.solmara.registrystack.org/v1/esignet/oauth/v2/token",
            "PORTAL_ESIGNET_USERINFO_ENDPOINT": "https://esignet.solmara.registrystack.org/v1/esignet/oidc/userinfo",
            "PORTAL_ESIGNET_REDIRECT_URI": "https://portal.solmara.registrystack.org/auth/callback",
            "PORTAL_ESIGNET_SCOPE": "openid profile",
            "PORTAL_ESIGNET_SUBJECT_CLAIM": "sub",
        }
        self.assertEqual(portal, expected)
        self.assertNotIn("name", overlay)

        private_key_value = "${PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64:?required}"
        self.assertEqual(
            {
                service_name
                for service_name, service in services.items()
                if service.get("environment", {}).get(
                    "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64"
                )
                == private_key_value
            },
            {"portal"},
        )
        self.assertEqual(
            services["esignet-seed"]["environment"]["ESIGNET_CLIENT_PRIVATE_KEY_B64"],
            private_key_value,
        )
        self.assertNotIn("SOLMARA_EVIDENCE_CLIENT_KEY", portal)
        self.assertNotIn("NIA_ESIGNET_CLIENT_PRIVATE_JWK", portal)

    def test_bruno_workspace_covers_only_the_eight_governed_v2_lookups(self) -> None:
        relay_requests = SCRIPT.parents[1] / "requests/registry-lab/50 - Relay V2"
        rendered = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(relay_requests.glob("*.bru"))
        )
        expected = {
            "/v2/resources/civil-person/lookups/death-by-uin",
            "/v2/resources/civil-person/lookups/citizen-link-by-uin",
            "/v2/resources/population-person/lookups/esignet-userinfo",
            "/v2/resources/beneficiary-enrolment/lookups/by-uin",
            "/v2/resources/pension-payment/lookups/by-pensioner-uin",
            "/v2/resources/survivor-case/lookups/by-spouse-uin",
            "/v2/resources/farmer/lookups/voucher-by-farmer-id",
            "/v2/resources/livestock-herd/lookups/movement-by-farmer-id",
        }
        self.assertEqual(len(list(relay_requests.glob("*.bru"))), len(expected))
        for path in expected:
            self.assertIn(path, rendered)
        self.assertNotIn("/records", rendered)
        self.assertNotIn("/search", rendered)
        self.assertNotIn("Data-Purpose", rendered)


if __name__ == "__main__":
    unittest.main()
