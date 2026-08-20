from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

SCRIPT = Path(__file__).with_name("check-runtime-topology.py")
SPEC = importlib.util.spec_from_file_location("runtime_topology", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimeTopologyTests(unittest.TestCase):
    def test_local_up_recreates_immutable_runtime_consumers(self) -> None:
        justfile = (SCRIPT.parents[1] / "justfile").read_text()
        for recipe in ("up: prepare", "up-esignet: prepare"):
            start = justfile.index(recipe)
            command = justfile[start:].splitlines()[1]
            self.assertIn("docker compose", command)
            self.assertIn("--force-recreate", command)

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
            self.assertEqual(service["user"], "65532:65532")
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", service["security_opt"])
            self.assertEqual(
                service["command"],
                ["serve", "--runtime", f"/etc/relay/{authority}/runtime.yaml"],
            )
            volumes = set(service["volumes"])
            self.assertIn(f"{authority}-relay-runtime:/etc/relay/{authority}:ro", volumes)
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
                service["depends_on"][f"{authority}-relay-runtime-stager"]["condition"],
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
        self.assertTrue(initializer["read_only"])
        self.assertEqual(initializer["restart"], "no")
        audit_init = initializer["command"][2]
        self.assertIn("os.scandir(path)", audit_init)
        self.assertIn("stat.S_ISREG", audit_init)
        self.assertIn("metadata.st_nlink != 1", audit_init)
        self.assertIn("audit\\.jsonl\\.\\d{8}", audit_init)
        self.assertIn("follow_symlinks=False", audit_init)
        self.assertIn("os.chown(path, 0, 0)", audit_init)
        self.assertIn("os.chown(path, target_uid, target_gid)", audit_init)
        self.assertIn(
            "os.chown(entry.path, target_uid, target_gid, follow_symlinks=False)",
            audit_init,
        )
        self.assertIn("target_uid = 65532", audit_init)
        self.assertIn("target_gid = 65532", audit_init)
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
            self.assertEqual(signer["cap_drop"], ["ALL"])
            self.assertEqual(signer["cap_add"], ["DAC_OVERRIDE"])
            self.assertEqual(signer["network_mode"], "none")
            self.assertIn("--allow-root-bind-owner", signer["command"])
            self.assertTrue(any(volume.endswith("signing.jwk:ro") for volume in signer["volumes"]))

    def test_local_authority_runtimes_use_owned_read_only_secret_volumes(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())

        services = {
            "mint": ("mint", "mint-runtime-secrets"),
            "cra-evidence": ("cra", "cra-evidence-runtime-secrets"),
            "nia-evidence": ("nia", "nia-evidence-runtime-secrets"),
            "sro-evidence": ("sro", "sro-evidence-runtime-secrets"),
            "mosd-programme-evidence": (
                "mosd-programme",
                "mosd-programme-evidence-runtime-secrets",
            ),
            "sipf-evidence": ("sipf", "sipf-evidence-runtime-secrets"),
            "nagdi-evidence": ("nagdi", "nagdi-evidence-runtime-secrets"),
        }
        for service_name, (provider, secret_volume) in services.items():
            service = compose["services"][service_name]
            self.assertEqual(service["user"], "0:0")
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertNotIn("cap_add", service)
            self.assertTrue(service["read_only"])
            secret_mounts = [
                volume
                for volume in service["volumes"]
                if "/run/secrets/" in volume
            ]
            self.assertEqual(len(secret_mounts), 1, service_name)
            self.assertTrue(
                secret_mounts[0].startswith(f"{secret_volume}:"), service_name
            )
            self.assertTrue(secret_mounts[0].endswith(":ro"), service_name)
            self.assertNotIn("./runtime/evidence-cells/secrets/", secret_mounts[0])
            self.assertEqual(
                service["depends_on"][f"{provider}-secret-stager"]["condition"],
                "service_completed_successfully",
            )
            self.assertEqual(
                service["depends_on"]["authority-audit-init"]["condition"],
                "service_completed_successfully",
            )

    def test_local_secret_stagers_are_authority_scoped_and_fail_closed(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())
        expected = {
            "mint": {"audit-hmac-key"},
            "cra": {
                "audit-hmac-key",
                "subject-binding-hmac-key",
                "cra-pension-evidence-client-id",
                "cra-pension-evidence-client-key",
                "cra-citizen-evidence-client-id",
                "cra-citizen-evidence-client-key",
            },
            "nia": {"audit-hmac-key", "subject-binding-hmac-key"},
            "sro": {"audit-hmac-key", "subject-binding-hmac-key"},
            "mosd-programme": {
                "audit-hmac-key",
                "subject-binding-hmac-key",
                "mosd-child-benefit-evidence-client-id",
                "mosd-child-benefit-evidence-client-key",
            },
            "sipf": {
                "audit-hmac-key",
                "subject-binding-hmac-key",
                "sipf-pension-evidence-client-id",
                "sipf-pension-evidence-client-key",
                "sipf-survivor-evidence-client-id",
                "sipf-survivor-evidence-client-key",
            },
            "nagdi": {
                "audit-hmac-key",
                "subject-binding-hmac-key",
                "nagdi-voucher-evidence-client-id",
                "nagdi-voucher-evidence-client-key",
                "nagdi-livestock-evidence-client-id",
                "nagdi-livestock-evidence-client-key",
            },
        }
        volumes = {
            "mint": "mint-runtime-secrets",
            "cra": "cra-evidence-runtime-secrets",
            "nia": "nia-evidence-runtime-secrets",
            "sro": "sro-evidence-runtime-secrets",
            "mosd-programme": "mosd-programme-evidence-runtime-secrets",
            "sipf": "sipf-evidence-runtime-secrets",
            "nagdi": "nagdi-evidence-runtime-secrets",
        }
        for provider, names in expected.items():
            stager = compose["services"][f"{provider}-secret-stager"]
            self.assertEqual(stager["command"][0], "stage")
            self.assertEqual(set(stager["command"][1:]), names)
            self.assertEqual(stager["user"], "0:0")
            self.assertTrue(stager["read_only"])
            self.assertEqual(stager["cap_drop"], ["ALL"])
            self.assertEqual(set(stager["cap_add"]), {"CHOWN", "DAC_OVERRIDE"})
            self.assertIn("no-new-privileges:true", stager["security_opt"])
            self.assertEqual(stager["network_mode"], "none")
            self.assertEqual(stager["restart"], "no")
            self.assertEqual(
                set(stager["volumes"]),
                {
                    f"./runtime/evidence-cells/secrets/{provider}:/source:ro",
                    f"{volumes[provider]}:/staged",
                },
            )

        command = compose["services"]["mint-secret-stager"]["entrypoint"][2]
        for required in (
            "set(source_entries) != expected",
            "stat.S_ISREG",
            "metadata.st_nlink != 1",
            "metadata.st_size > max_secret_bytes",
            "opened.st_size > max_secret_bytes",
            "max_secret_bytes = 64 * 1024",
            "if copied > max_secret_bytes",
            "{0o400, 0o600}",
            "os.O_NOFOLLOW",
            "os.fchown(destination_fd, 0, 0)",
            "os.fchmod(destination_fd, 0o700)",
            "os.fchown(destination, 0, 0)",
            "os.fchmod(destination, 0o600)",
            "os.replace",
        ):
            self.assertIn(required, command)
        self.assertNotIn("print(", command)

    def test_local_secret_stager_copies_without_rendering_secret_values(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())
        command = compose["services"]["mint-secret-stager"]["entrypoint"][2]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "staged"
            source.mkdir()
            destination.mkdir()
            secret = source / "audit-hmac-key"
            secret.write_bytes(b"secret-canary\n")
            secret.chmod(0o600)
            patched = command.replace("'/source'", repr(str(source))).replace(
                "'/staged'", repr(str(destination))
            )
            with (
                mock.patch("sys.argv", ["-c", "stage", "audit-hmac-key"]),
                mock.patch("os.fchown"),
            ):
                exec(patched, {})

            staged = destination / "audit-hmac-key"
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
            self.assertEqual(staged.read_bytes(), b"secret-canary\n")
            self.assertEqual(stat.S_IMODE(staged.stat().st_mode), 0o600)
            self.assertEqual(staged.stat().st_nlink, 1)

            peer = root / "peer"
            os.link(secret, peer)
            with (
                mock.patch("sys.argv", ["-c", "stage", "audit-hmac-key"]),
                mock.patch("os.fchown"),
                self.assertRaisesRegex(
                    RuntimeError, "secret source has unsafe metadata"
                ),
            ):
                exec(patched, {})

            peer.unlink()
            secret.write_bytes(b"x" * (64 * 1024 + 1))
            with (
                mock.patch("sys.argv", ["-c", "stage", "audit-hmac-key"]),
                mock.patch("os.fchown"),
                self.assertRaisesRegex(
                    RuntimeError, "secret source has unsafe metadata"
                ),
            ):
                exec(patched, {})

    def test_local_authority_audit_initializer_is_metadata_only_and_isolated(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())
        initializer = compose["services"]["authority-audit-init"]

        self.assertEqual(initializer["network_mode"], "none")
        self.assertEqual(initializer["user"], "0:0")
        self.assertEqual(initializer["cap_drop"], ["ALL"])
        self.assertEqual(set(initializer["cap_add"]), {"CHOWN", "FOWNER"})
        self.assertIn("no-new-privileges:true", initializer["security_opt"])
        self.assertTrue(initializer["read_only"])
        self.assertEqual(initializer["restart"], "no")
        self.assertEqual(
            set(initializer["volumes"]),
            {
                "mint-v2-audit:/audit/mint",
                "cra-evidence-audit:/audit/cra",
                "nia-evidence-audit:/audit/nia",
                "sro-evidence-audit:/audit/sro",
                "mosd-evidence-audit:/audit/mosd-programme",
                "sipf-evidence-audit:/audit/sipf",
                "nagdi-evidence-audit:/audit/nagdi",
            },
        )
        command = initializer["command"][2]
        self.assertIn("os.lstat(path)", command)
        self.assertIn("stat.S_ISDIR", command)
        self.assertIn("os.chown(path, 0, 0)", command)
        self.assertIn("mint_chain = '/audit/mint/audit'", command)
        self.assertIn("os.mkdir(mint_chain, 0o700)", command)
        self.assertIn("os.lstat(mint_chain)", command)
        self.assertIn("with os.scandir(path) as entries", command)
        self.assertIn("entry.stat(follow_symlinks=False)", command)
        self.assertIn("metadata.st_nlink != 1", command)
        self.assertIn("re.escape(active_name) + r'\\.\\d{8}'", command)
        self.assertIn("os.chown(entry.path, 0, 0", command)
        self.assertNotIn("os.chown(mint_chain, 65532, 65532)", command)
        self.assertNotIn("os.chown(path, 65532, 65532)", command)

    def test_local_authority_audit_initializer_rejects_unsafe_known_files(self) -> None:
        compose = yaml.safe_load((SCRIPT.parents[1] / "compose.yaml").read_text())
        command = compose["services"]["authority-audit-init"]["command"][2]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            providers = (
                "mint",
                "cra",
                "nia",
                "sro",
                "mosd-programme",
                "sipf",
                "nagdi",
            )
            paths = [root / provider for provider in providers]
            for path in paths:
                path.mkdir()
            mint_chain = paths[0] / "audit"
            patched = command.replace(
                "['/audit/mint', '/audit/cra', '/audit/nia', '/audit/sro', '/audit/mosd-programme', '/audit/sipf', '/audit/nagdi']",
                repr([str(path) for path in paths]),
            ).replace("'/audit/mint/audit'", repr(str(mint_chain)))
            for original, replacement in zip(
                (
                    "/audit/cra",
                    "/audit/nia",
                    "/audit/sro",
                    "/audit/mosd-programme",
                    "/audit/sipf",
                    "/audit/nagdi",
                ),
                paths[1:],
                strict=True,
            ):
                patched = patched.replace(repr(original), repr(str(replacement)))

            target = root / "target"
            target.write_text("audit-canary\n", encoding="utf-8")
            unsafe = paths[1] / "evidence.jsonl"
            unsafe.symlink_to(target)
            with (
                mock.patch("os.chown"),
                mock.patch("os.chmod"),
                self.assertRaisesRegex(
                    RuntimeError, "audit sink has unsafe metadata"
                ),
            ):
                exec(patched, {})

            unsafe.unlink()
            os.link(target, unsafe)
            with (
                mock.patch("os.chown"),
                mock.patch("os.chmod"),
                self.assertRaisesRegex(
                    RuntimeError, "audit sink has unsafe metadata"
                ),
            ):
                exec(patched, {})

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
            service = services[f"{authority}_relay"]
            self.assertEqual(
                service["command"],
                ["serve", "--runtime", f"/etc/relay/{authority}/runtime.yaml"],
            )
            volumes = set(service["volumes"])
            self.assertIn(
                f"/data/solmara-authority-cells/{authority}-relay/runtime:/etc/relay/{authority}:ro",
                volumes,
            )
            self.assertIn(
                f"/data/solmara-authority-cells/{authority}-relay/source:/var/lib/relay/source:ro",
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
        for service_name in ("scenario_runner", "child_benefit_federator", "portal"):
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
            services["scenario_runner"]["environment"]["CHILD_BENEFIT_FEDERATOR_URL"],
            "${SOLMARA_CHILD_BENEFIT_FEDERATOR_PUBLIC_BASE_URL:-https://child-benefit.solmara.registrystack.org}",
        )
        self.assertEqual(
            services["portal"]["environment"]["CHILD_BENEFIT_FEDERATOR_URL"],
            "${SOLMARA_CHILD_BENEFIT_FEDERATOR_PUBLIC_BASE_URL:-https://child-benefit.solmara.registrystack.org}",
        )
        self.assertEqual(
            services["child_benefit_federator"]["environment"][
                "CHILD_BENEFIT_FEDERATOR_HOST"
            ],
            "0.0.0.0",
        )
        self.assertEqual(
            services["child_benefit_federator"]["environment"][
                "CHILD_BENEFIT_FEDERATOR_PORT"
            ],
            "8080",
        )

        for service_name in ("home", "static_metadata"):
            service = services[service_name]
            self.assertNotIn("secrets", service, service_name)
            environment = service.get("environment", {})
            self.assertNotIn("SOLMARA_EVIDENCE_CLIENT_KEY", environment, service_name)
            self.assertNotIn("CHILD_BENEFIT_FEDERATOR_TOKEN", environment, service_name)

    def test_hosted_esignet_is_standalone_and_core_portal_owns_login_config(
        self,
    ) -> None:
        esignet_path = SCRIPT.parents[1] / "compose.coolify.esignet.yaml"
        esignet = yaml.safe_load(esignet_path.read_text(encoding="utf-8"))
        services = esignet["services"]
        self.assertEqual(
            set(services),
            {
                "esignet-database",
                "esignet-redis",
                "esignet",
                "esignet_ui",
                "esignet_edge",
                "esignet-seed",
            },
        )
        self.assertNotIn("portal", services)

        core = yaml.safe_load(
            (SCRIPT.parents[1] / "compose.coolify.yaml").read_text(encoding="utf-8")
        )
        portal = core["services"]["portal"]["environment"]
        expected = {
            "PORTAL_AUTH_PROVIDER": "${PORTAL_AUTH_PROVIDER:-mock}",
            "PORTAL_SECURE_COOKIES": "true",
            "PORTAL_ESIGNET_CLIENT_ID": "${PORTAL_ESIGNET_CLIENT_ID:-solmara-portal}",
            "PORTAL_ESIGNET_CLIENT_KEY_ID": "${PORTAL_ESIGNET_CLIENT_KEY_ID:-solmara-portal-key-1}",
            "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64": "${PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64:-}",
            "PORTAL_ESIGNET_ISSUER": "${SOLMARA_ESIGNET_PUBLIC_BASE_URL:-https://esignet.solmara.registrystack.org}",
            "PORTAL_ESIGNET_AUTHORIZATION_ENDPOINT": "${SOLMARA_ESIGNET_UI_PUBLIC_BASE_URL:-https://esignet-ui.solmara.registrystack.org}/authorize",
            "PORTAL_ESIGNET_TOKEN_ENDPOINT": "${SOLMARA_ESIGNET_PUBLIC_BASE_URL:-https://esignet.solmara.registrystack.org}/v1/esignet/oauth/v2/token",
            "PORTAL_ESIGNET_CLIENT_ASSERTION_AUDIENCE": "${SOLMARA_ESIGNET_PUBLIC_BASE_URL:-https://esignet.solmara.registrystack.org}/v1/esignet/oauth/v2/token",
            "PORTAL_ESIGNET_USERINFO_ENDPOINT": "${SOLMARA_ESIGNET_PUBLIC_BASE_URL:-https://esignet.solmara.registrystack.org}/v1/esignet/oidc/userinfo",
            "PORTAL_ESIGNET_REDIRECT_URI": "${SOLMARA_PORTAL_PUBLIC_BASE_URL:-https://portal.solmara.registrystack.org}/auth/callback",
            "PORTAL_ESIGNET_SCOPE": "openid profile",
            "PORTAL_ESIGNET_SUBJECT_CLAIM": "sub",
        }
        for key, value in expected.items():
            self.assertEqual(portal[key], value)

        private_key_value = "${PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64:-}"
        self.assertEqual(
            {
                service_name
                for service_name, service in core["services"].items()
                if service.get("environment", {}).get(
                    "PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64"
                )
                == private_key_value
            },
            {"portal"},
        )
        self.assertEqual(
            services["esignet-seed"]["environment"]["ESIGNET_CLIENT_PRIVATE_KEY_B64"],
            "${PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64:?required}",
        )
        self.assertNotIn("NIA_ESIGNET_CLIENT_PRIVATE_JWK", portal)

    def test_hosted_esignet_seeder_runs_once(self) -> None:
        """Coolify gives a service that declares no restart policy
        `unless-stopped`, so a one-shot that exits on success is started again
        forever. Every other one-shot in the fleet says `no`; the seeder must
        too."""
        esignet_path = SCRIPT.parents[1] / "compose.coolify.esignet.yaml"
        esignet = yaml.safe_load(esignet_path.read_text(encoding="utf-8"))
        self.assertEqual(esignet["services"]["esignet-seed"].get("restart"), "no")

    def test_hosted_esignet_publishes_discovery_at_its_issuer_root(self) -> None:
        """eSignet declares its issuer as the bare public origin but the Spring
        service answers only under `/v1/esignet`, so routing the public host
        straight at it leaves `{issuer}/.well-known/openid-configuration` and the
        RFC 8414 authorization-server document unserved. The UI image is a
        host-agnostic reverse proxy that publishes both, so the public host
        belongs to an edge instance of it and the service stays unrouted.

        Both proxies carry underscore names because Coolify accepts a routed
        service only under its compose key but resolves it after rewriting "-"
        to "_", so a hyphenated name is stored where routing never reads."""
        esignet_path = SCRIPT.parents[1] / "compose.coolify.esignet.yaml"
        services = yaml.safe_load(esignet_path.read_text(encoding="utf-8"))["services"]
        edge = services["esignet_edge"]
        self.assertEqual(edge["image"], services["esignet_ui"]["image"])
        self.assertEqual(
            edge["labels"]["solmara.lab.host"],
            "${SOLMARA_ESIGNET_PUBLIC_HOST:-esignet.solmara.registrystack.org}",
        )
        self.assertNotIn("solmara.lab.host", services["esignet"].get("labels") or {})
        routed = [
            name
            for name, service in services.items()
            if "solmara.lab.host" in (service.get("labels") or {})
        ]
        self.assertEqual(sorted(routed), ["esignet_edge", "esignet_ui"])
        for name in routed:
            self.assertNotIn("-", name)

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
