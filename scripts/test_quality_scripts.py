from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_smoke_live():
    spec = importlib.util.spec_from_file_location(
        "smoke_live", ROOT / "scripts" / "smoke-live.py"
    )
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


def load_config_secret_check():
    spec = importlib.util.spec_from_file_location(
        "check_config_secrets", ROOT / "scripts" / "check-config-secrets.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load check-config-secrets.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_config_secrets"] = module
    spec.loader.exec_module(module)
    return module


def load_secret_generator():
    load_compose_project_name()
    spec = importlib.util.spec_from_file_location(
        "solmara_gen_secrets", ROOT / "scripts" / "gen-secrets.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load gen-secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityScriptTests(unittest.TestCase):
    def test_performance_guide_references_every_k6_entrypoint(self) -> None:
        guide = (ROOT / "perf" / "README.md").read_text(encoding="utf-8")
        referenced = set(re.findall(r"perf/k6/[A-Za-z0-9_.-]+\.js", guide))
        entrypoints = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "perf" / "k6").glob("*.js")
        }
        self.assertEqual(referenced, entrypoints)

    def test_authority_notary_cel_ceiling_is_explicit_and_generated(self) -> None:
        projects = (
            "cra-civil",
            "nia-population",
            "sro-social",
            "mosd-programme",
            "sipf-pensions",
            "nagdi-agriculture",
        )
        for environment in ("local", "hosted"):
            for project in projects:
                with self.subTest(environment=environment, project=project):
                    authored = yaml.safe_load(
                        (
                            ROOT
                            / "projects"
                            / project
                            / "environments"
                            / f"{environment}.yaml"
                        ).read_text(encoding="utf-8")
                    )
                    generated = yaml.safe_load(
                        (
                            ROOT
                            / "runtime"
                            / "registry-projects"
                            / environment
                            / project
                            / "notary"
                            / "notary.yaml"
                        ).read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        authored["notary_cel"],
                        {"worker_memory_bytes": 1_073_741_824},
                    )
                    self.assertEqual(generated["cel"], authored["notary_cel"])

    def test_generated_secret_contract_uses_authority_owners(self) -> None:
        module = load_secret_generator()
        self.assertEqual(
            set(module.RAW_HASH_PAIRS),
            {
                (
                    "CRA_CHILD_BENEFIT_CLIENT_TOKEN",
                    "CRA_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                ),
                ("CRA_PENSION_CLIENT_TOKEN", "CRA_PENSION_CLIENT_TOKEN_HASH"),
                ("CRA_CITIZEN_CLIENT_TOKEN", "CRA_CITIZEN_CLIENT_TOKEN_HASH"),
                (
                    "NIA_CHILD_BENEFIT_CLIENT_TOKEN",
                    "NIA_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                ),
                ("NIA_CITIZEN_CLIENT_TOKEN", "NIA_CITIZEN_CLIENT_TOKEN_HASH"),
                (
                    "SRO_CHILD_BENEFIT_CLIENT_TOKEN",
                    "SRO_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                ),
                (
                    "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
                    "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                ),
                ("SIPF_PENSION_CLIENT_TOKEN", "SIPF_PENSION_CLIENT_TOKEN_HASH"),
                ("NAGDI_NOTARY_TOKEN", "NAGDI_CLIENT_TOKEN_HASH"),
            },
        )
        self.assertEqual(
            set(module.JWK_KIDS),
            {
                "CRA_RELAY_WORKLOAD_JWK",
                "NIA_RELAY_WORKLOAD_JWK",
                "NIA_ESIGNET_RELAY_WORKLOAD_JWK",
                "SRO_RELAY_WORKLOAD_JWK",
                "PROGRAMME_RELAY_WORKLOAD_JWK",
                "SIPF_RELAY_WORKLOAD_JWK",
                "NAGDI_RELAY_WORKLOAD_JWK",
                "NIA_NOTARY_ISSUER_JWK",
                "SIPF_NOTARY_ISSUER_JWK",
                "NAGDI_NOTARY_ISSUER_JWK",
            },
        )

        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            module.ROOT = temporary_root
            module.POSTGRES_SSL_DIR = temporary_root / "config" / "postgres" / "ssl"
            module.compose_project_name = lambda _root: "solmara-lab-test"
            federation_output = temporary_root / "federation.env"
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as rejected:
                    module.main(["--federation-output", str(federation_output)])
            self.assertEqual(rejected.exception.code, 2)
            self.assertFalse(federation_output.exists())

            self.assertEqual(module.main([]), 0)
            output = temporary_root / ".env"
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

            generated_keys = {
                line.split("=", 1)[0]
                for line in output.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#")
            }
            declared_keys = {
                line.split("=", 1)[0]
                for line in (ROOT / ".env.example")
                .read_text(encoding="utf-8")
                .splitlines()
                if line and not line.startswith("#") and "=" in line
            }
            self.assertEqual(generated_keys - declared_keys, set())

            retired_names = {
                "CIVIL_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "NIA_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "SRO_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "PROGRAMME_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "PENSION_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "CITIZEN_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "CITIZEN_ISSUER_NOTARY_POSTGRES_RUNTIME_PASSWORD",
                "PENSION_NOTARY_TOKEN",
                "PORTAL_CITIZEN_NOTARY_TOKEN",
                "PORTAL_RELAY_TOKEN",
                "SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW",
                "SOLMARA_ESIGNET_IDENTITY_RELEASE_HASH",
                "CHILD_BENEFIT_PUBLIC_DOMAIN",
                "CHILD_BENEFIT_FEDERATOR_REQUEST_JWK",
                "CIVIL_CHILD_BENEFIT_PAIRWISE_SECRET",
                "PENSION_NOTARY_ISSUER_JWK",
                "CITIZEN_NOTARY_ISSUER_JWK",
                "CITIZEN_ISSUER_ESIGNET_RP_JWK",
                "CIVIL_CHILD_BENEFIT_NOTARY_URL",
                "PENSION_NOTARY_URL",
                "PORTAL_CIVIL_RELAY_URL",
            }
            self.assertEqual(retired_names & generated_keys, set())
            self.assertEqual(retired_names & declared_keys, set())
            self.assertEqual(
                {
                    name
                    for name in generated_keys | declared_keys
                    if name.endswith(("_SOURCE_RAW", "_SOURCE_HASH"))
                },
                set(),
            )

    def test_workload_issuer_contract_is_bounded_and_esignet_isolated(self) -> None:
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        services = compose["services"]
        expected = {
            "cra-workload-agent": (
                "cra-notary",
                {
                    "registry:consult:cra-child-benefit",
                    "registry:consult:cra-citizen-record",
                    "registry:consult:cra-pension-death",
                },
            ),
            "nia-workload-agent": (
                "nia-notary",
                {
                    "registry:consult:nia-child-benefit",
                    "registry:consult:nia-citizen-status",
                },
            ),
            "sro-workload-agent": (
                "sro-notary",
                {"registry:consult:child-benefit"},
            ),
            "programme-workload-agent": (
                "programme-notary",
                {"registry:consult:child-benefit"},
            ),
            "sipf-workload-agent": (
                "sipf-notary",
                {
                    "registry:consult:sipf-pension-payment-review",
                    "registry:consult:sipf-survivor-benefit",
                },
            ),
            "nagdi-workload-agent": (
                "nagdi-notary",
                {"registry:consult:livestock", "registry:consult:voucher"},
            ),
        }
        for service_name, (client_id, scopes) in expected.items():
            with self.subTest(service=service_name):
                environment = services[service_name]["environment"]
                identities = json.loads(environment["WORKLOAD_IDENTITIES_JSON"])
                notary = next(
                    identity for identity in identities if identity["azp"] == client_id
                )
                self.assertEqual(notary["subject"], client_id)
                self.assertEqual(notary["audience"], "registry-relay")
                self.assertEqual(set(notary["scopes"]), scopes)
                self.assertEqual(
                    notary["token_file"], f"/run/secrets/{client_id}-relay-token"
                )
                self.assertEqual(
                    len({identity["azp"] for identity in identities}), len(identities)
                )
                self.assertEqual(
                    len({identity["subject"] for identity in identities}),
                    len(identities),
                )
                self.assertEqual(
                    len({identity["token_file"] for identity in identities}),
                    len(identities),
                )
                for retired in (
                    "WORKLOAD_AUDIENCE",
                    "WORKLOAD_AZP",
                    "WORKLOAD_SUB",
                    "WORKLOAD_SCOPE",
                    "WORKLOAD_TOKEN_FILE",
                    "WORKLOAD_PRIVATE_JWK_ENV",
                ):
                    self.assertNotIn(retired, environment)

        nia_identities = json.loads(
            services["nia-workload-agent"]["environment"]["WORKLOAD_IDENTITIES_JSON"]
        )
        self.assertEqual(len(nia_identities), 2)
        esignet_identity = next(
            identity
            for identity in nia_identities
            if identity["azp"] == "solmara-esignet"
        )
        self.assertEqual(esignet_identity["subject"], "solmara-esignet")
        self.assertEqual(esignet_identity["scopes"], ["population:identity_release"])
        self.assertEqual(esignet_identity["token_uid"], 1001)
        self.assertEqual(esignet_identity["token_gid"], 1001)
        self.assertEqual(
            esignet_identity["token_file"],
            "/run/esignet-secrets/solmara-esignet-relay-token",
        )
        self.assertEqual(
            esignet_identity["private_jwk_env"],
            "NIA_ESIGNET_RELAY_WORKLOAD_JWK",
        )
        self.assertIn(
            "nia-esignet-workload-token:/run/esignet-secrets",
            services["nia-workload-agent"]["volumes"],
        )
        self.assertNotIn(
            "nia-esignet-workload-token:/run/esignet-secrets",
            services["nia-notary"]["volumes"],
        )

        local_esignet = yaml.safe_load(
            (ROOT / "compose.esignet.yaml").read_text(encoding="utf-8")
        )["services"]["esignet"]
        hosted_compose = yaml.safe_load(
            (ROOT / "compose.coolify.esignet.yaml").read_text(encoding="utf-8")
        )
        hosted_esignet = hosted_compose["services"]["esignet"]
        for esignet in (local_esignet, hosted_esignet):
            self.assertEqual(
                esignet["environment"]["REGISTRY_RELAY_AUTH_BEARER_TOKEN_FILE"],
                "/run/secrets/solmara-esignet-relay-token",
            )
            self.assertNotIn("REGISTRY_RELAY_AUTH_BEARER_TOKEN", esignet["environment"])
            self.assertNotIn(
                "REGISTRY_RELAY_AUTH_CREDENTIAL_KIND", esignet["environment"]
            )
            self.assertIn(
                "nia-esignet-workload-token:/run/secrets:ro", esignet["volumes"]
            )
        self.assertEqual(
            local_esignet["depends_on"]["nia-workload-agent"]["condition"],
            "service_healthy",
        )
        self.assertNotIn("ports", local_esignet)
        local_esignet_edge = yaml.safe_load(
            (ROOT / "compose.esignet.yaml").read_text(encoding="utf-8")
        )["services"]["esignet-edge"]
        self.assertEqual(
            local_esignet_edge["ports"], ["${SOLMARA_ESIGNET_PORT:-4308}:3000"]
        )
        self.assertEqual(
            local_esignet_edge["depends_on"]["esignet"]["condition"],
            "service_healthy",
        )
        self.assertIn(
            "config/esignet/nginx.conf",
            local_esignet_edge["build"]["args"]["ESIGNET_NGINX_CONF"],
        )
        self.assertEqual(
            hosted_compose["volumes"]["nia-esignet-workload-token"],
            {
                "external": True,
                "name": "${NIA_ESIGNET_WORKLOAD_TOKEN_VOLUME:-solmara-nia-esignet-workload-token}",
            },
        )

        hosted_interior = yaml.safe_load(
            (ROOT / "compose.coolify.interior.yaml").read_text(encoding="utf-8")
        )
        for service_name in ("nia-notary", "nia-notary-state-install"):
            self.assertTrue(
                all(
                    "nia-esignet-workload-token" not in volume
                    for volume in hosted_interior["services"][service_name]["volumes"]
                )
            )

        retired_static_names = {
            "SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW",
            "SOLMARA_ESIGNET_IDENTITY_RELEASE_HASH",
        }
        self.assertTrue(
            retired_static_names.isdisjoint(
                name for pair in load_secret_generator().RAW_HASH_PAIRS for name in pair
            )
        )

    def test_esignet_identity_input_resolves_the_nia_uin(self) -> None:
        project = yaml.safe_load(
            (ROOT / "projects" / "nia-population" / "registry-stack.yaml").read_text(
                encoding="utf-8"
            )
        )
        authored_profile = project["services"]["nia-population-records"]["api"][
            "attribute_release_profiles"
        ]["solmara-nia-userinfo"]
        self.assertEqual(authored_profile["subject"]["input"], "individual_id")
        self.assertEqual(authored_profile["subject"]["source_field"], "uin")
        self.assertEqual(
            authored_profile["claims"]["individual_id"]["source_field"], "uin"
        )

        for environment in ("local", "hosted"):
            relay = yaml.safe_load(
                (
                    ROOT
                    / "runtime"
                    / "registry-projects"
                    / environment
                    / "nia-population"
                    / "relay"
                    / "relay.yaml"
                ).read_text(encoding="utf-8")
            )
            population = next(
                entity
                for dataset in relay["datasets"]
                for entity in dataset["entities"]
                if entity["name"] == "population"
            )
            generated_profile = next(
                profile
                for profile in population["attribute_release_profiles"]
                if profile["id"] == "solmara-nia-userinfo"
            )
            self.assertEqual(generated_profile["subject"]["source_field"], "uin")

        population_fixture = (
            ROOT
            / "ministries"
            / "interior-population"
            / "fixtures"
            / "population_person.csv"
        )
        with population_fixture.open(encoding="utf-8", newline="") as fixture:
            elena = next(
                row for row in csv.DictReader(fixture) if row["uin"] == "2300018263"
            )
        self.assertEqual(
            (elena["given_name"], elena["family_name"]), ("Elena", "Dela Cruz")
        )

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

    def test_secret_lint_scans_runtime_and_limits_workload_volume_exemption(
        self,
    ) -> None:
        module = load_config_secret_check()
        scanned = {path.relative_to(ROOT).as_posix() for path in module.iter_files()}
        self.assertIn(
            "runtime/registry-projects/local/cra-civil/notary/notary.yaml",
            scanned,
        )
        self.assertIn("projects/cra-civil/environments/local.yaml", scanned)
        self.assertFalse(any(path.startswith("notaries/") for path in scanned))
        self.assertFalse(any(path.startswith("hosted/notaries/") for path in scanned))
        self.assertTrue(
            module.line_is_allowed("      - cra-workload-token:/run/secrets:ro")
        )
        self.assertTrue(
            module.line_is_allowed(
                "      - nia-esignet-workload-token:/run/esignet-secrets"
            )
        )
        self.assertTrue(
            module.line_is_allowed(
                "    api_key_fingerprint: { secret: CRA_CHILD_BENEFIT_CLIENT_TOKEN_HASH }"
            )
        )
        self.assertFalse(
            module.line_is_allowed("token: leaked-cra-notary-workload-token:value")
        )
        self.assertFalse(module.line_is_allowed("signing_key: a-raw-private-key"))

    def test_registry_projects_are_explicit_and_use_the_pinned_registryctl(
        self,
    ) -> None:
        required_version = next(
            line.split("=", 1)[1]
            for line in (ROOT / "versions.env").read_text(encoding="utf-8").splitlines()
            if line.startswith("REGISTRYCTL_VERSION=")
        )
        projects = [
            "cra-civil",
            "nia-population",
            "sro-social",
            "mosd-programme",
            "sipf-pensions",
            "nagdi-agriculture",
        ]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            registryctl = temporary / "registryctl"
            log = temporary / "commands.log"
            registryctl.write_text(
                f"""#!/bin/sh
if [ "${1:-}" = "--version" ]; then
  echo "registryctl {required_version}"
  exit 0
fi
if [ "${2:-}" = "--help" ]; then
  case "${1:-}" in
    check | test | build) exit 0 ;;
  esac
fi
printf '%s\\n' "$*" >> "$REGISTRYCTL_LOG"
""",
                encoding="utf-8",
            )
            registryctl.chmod(0o755)
            result = subprocess.run(
                [str(ROOT / "scripts" / "registry-projects.sh"), "check"],
                cwd=ROOT,
                env={
                    **os.environ,
                    "REGISTRYCTL_BIN": str(registryctl),
                    "REGISTRYCTL_LOG": str(log),
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = log.read_text(encoding="utf-8").splitlines()
            expected = [
                f"check --project-dir {ROOT / 'projects' / project} --environment {environment}"
                for project in projects
                for environment in ("local", "hosted")
            ]
            self.assertEqual(commands, expected)

            registryctl.write_text(
                "#!/bin/sh\necho 'registryctl 0.8.3'\n",
                encoding="utf-8",
            )
            rejected = subprocess.run(
                [str(ROOT / "scripts" / "registry-projects.sh"), "check"],
                cwd=ROOT,
                env={**os.environ, "REGISTRYCTL_BIN": str(registryctl)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn(
                f"registryctl {required_version} is required", rejected.stderr
            )

            registryctl.write_text(
                f'#!/bin/sh\nif [ "${{1:-}}" = "--version" ]; then echo \'registryctl {required_version}\'; exit 0; fi\nexit 1\n',
                encoding="utf-8",
            )
            incompatible = subprocess.run(
                [str(ROOT / "scripts" / "registry-projects.sh"), "check"],
                cwd=ROOT,
                env={**os.environ, "REGISTRYCTL_BIN": str(registryctl)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(incompatible.returncode, 1)
            self.assertIn(
                "with project-authoring check/test/build is required",
                incompatible.stderr,
            )

    def test_registry_project_secret_references_have_local_producers(self) -> None:
        module = load_secret_generator()
        produced = (
            {hashed for _, hashed in module.RAW_HASH_PAIRS}
            | set(module.JWK_KIDS)
            | module.DIRECT_PROJECT_SECRET_NAMES
        )
        declared = {
            line.split("=", 1)[0]
            for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        consumed = set()

        def collect(value) -> None:
            if isinstance(value, dict):
                if set(value) == {"secret"} and isinstance(value["secret"], str):
                    consumed.add(value["secret"])
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        for environment in sorted((ROOT / "projects").glob("*/environments/*.yaml")):
            collect(yaml.safe_load(environment.read_text(encoding="utf-8")))

        self.assertEqual(consumed - produced, set())
        self.assertEqual(consumed - declared, set())

    def test_coolify_authority_state_is_postgresql_isolated(self) -> None:
        authority_groups = {
            "compose.coolify.interior.yaml": (
                "nia",
                (
                    ("cra", "cra-civil", "cra-civil-relay", "cra-notary"),
                    ("nia", "nia-population", "nia-population-relay", "nia-notary"),
                ),
            ),
            "compose.coolify.social-development.yaml": (
                "",
                (
                    ("sro", "sro-social", "sro-social-relay", "sro-notary"),
                    (
                        "programme",
                        "mosd-programme",
                        "programme-mis-relay",
                        "programme-notary",
                    ),
                ),
            ),
            "compose.coolify.labour-pensions.yaml": (
                "sipf",
                (("sipf", "sipf-pensions", "sipf-pensions-relay", "sipf-notary"),),
            ),
            "compose.coolify.agriculture.yaml": (
                "",
                (
                    (
                        "nagdi",
                        "nagdi-agriculture",
                        "nagdi-agriculture-relay",
                        "nagdi-notary",
                    ),
                ),
            ),
        }

        for compose_name, (source_readers, authorities) in authority_groups.items():
            with self.subTest(compose=compose_name):
                compose = yaml.safe_load(
                    (ROOT / compose_name).read_text(encoding="utf-8")
                )
                declared_volumes = set((compose.get("volumes") or {}).keys())
                services = compose["services"]
                self.assertNotIn("redis", services)
                self.assertIn("postgres-data", declared_volumes)
                self.assertIn(
                    "postgres-data:/var/lib/postgresql/data",
                    services["postgres"]["volumes"],
                )
                postgres_env = services["postgres"]["environment"]
                authority_keys = [authority[0] for authority in authorities]
                self.assertEqual(
                    postgres_env["SOLMARA_RELAY_DATABASES"].split(), authority_keys
                )
                self.assertEqual(
                    postgres_env["SOLMARA_NOTARY_DATABASES"].split(), authority_keys
                )
                self.assertEqual(
                    postgres_env["SOLMARA_SOURCE_READER_DATABASES"], source_readers
                )
                self.assertEqual(
                    services["registry-postgresql-bootstrap"]["restart"], "no"
                )
                for service_name, service in services.items():
                    for mount in service.get("volumes") or []:
                        with self.subTest(service=service_name, mount=mount):
                            self.assertIn(
                                mount.split(":", 1)[0],
                                declared_volumes,
                                "Coolify authority services must use named volumes; "
                                "repository bind mounts are not deployable closures",
                            )

                for key, project, relay_name, notary_name in authorities:
                    with self.subTest(authority=key):
                        relay = services[relay_name]
                        notary = services[notary_name]
                        installer = services[f"{notary_name}-state-install"]
                        bootstrap = services[f"{key}-relay-state-bootstrap"]
                        relay_mounts = set(relay.get("volumes") or [])
                        notary_mounts = set(notary.get("volumes") or [])
                        relay_config = (
                            f"/etc/solmara/registry-projects/hosted/{project}/relay/relay.yaml"
                        )
                        notary_config = (
                            f"/etc/solmara/registry-projects/hosted/{project}/notary/notary.yaml"
                        )
                        self.assertEqual(relay["command"], ["--config", relay_config])
                        self.assertEqual(
                            bootstrap["command"][
                                bootstrap["command"].index("--config") + 1
                            ],
                            relay_config,
                        )
                        self.assertIn(f"{key}-relay-cache", declared_volumes)
                        self.assertIn(
                            f"{key}-relay-cache:/var/lib/registry-relay/cache",
                            relay_mounts,
                        )
                        self.assertEqual(
                            notary["command"], ["--config", notary_config]
                        )
                        self.assertEqual(
                            installer["command"][
                                installer["command"].index("--config") + 1
                            ],
                            notary_config,
                        )
                        self.assertEqual(
                            notary["network_mode"], f"service:{relay_name}"
                        )
                        self.assertEqual(notary["user"], "65534:65534")
                        self.assertNotIn(
                            "REGISTRY_NOTARY_POSTGRES_MIGRATOR_URL",
                            notary["environment"],
                        )
                        self.assertIn(
                            "REGISTRY_NOTARY_POSTGRES_MIGRATOR_URL",
                            installer["environment"],
                        )
                        self.assertEqual(installer["restart"], "no")
                        self.assertEqual(
                            notary["depends_on"][f"{notary_name}-state-install"][
                                "condition"
                            ],
                            "service_completed_successfully",
                        )
                        self.assertEqual(
                            notary["labels"]["solmara.lab.host"],
                            f"{notary_name}.solmara.registrystack.org",
                        )
                        self.assertFalse(
                            any(
                                "/var/lib/registry-notary" in mount
                                for mount in notary_mounts
                            )
                        )

    def test_hosted_authority_images_contain_runtime_closures_and_tls(self) -> None:
        relay_dockerfile = (ROOT / "docker" / "relay" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        notary_dockerfile = (
            ROOT / "docker" / "notary" / "Dockerfile"
        ).read_text(encoding="utf-8")
        projects = (
            "cra-civil",
            "nia-population",
            "sro-social",
            "mosd-programme",
            "sipf-pensions",
            "nagdi-agriculture",
        )
        for project in projects:
            with self.subTest(project=project):
                self.assertIn(
                    f"COPY runtime/registry-projects/hosted/{project}/relay "
                    f"/etc/solmara/registry-projects/hosted/{project}/relay",
                    relay_dockerfile,
                )
                self.assertIn(
                    f"COPY runtime/registry-projects/hosted/{project}/notary/notary.yaml "
                    f"/etc/solmara/registry-projects/hosted/{project}/notary/notary.yaml",
                    notary_dockerfile,
                )
        tls_copy = (
            "COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt"
        )
        self.assertIn(tls_copy, relay_dockerfile)
        self.assertIn(tls_copy, notary_dockerfile)

    def test_hosted_postgresql_image_contains_both_live_source_fixtures(self) -> None:
        dockerfile = (ROOT / "docker" / "postgres" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "COPY ministries/interior-population/fixtures /docker-entrypoint-initdb.d",
            dockerfile,
        )
        self.assertIn(
            "COPY ministries/labour-pensions/fixtures /docker-entrypoint-initdb.d",
            dockerfile,
        )

    def test_notary_postgresql_state_is_isolated_and_redis_free(self) -> None:
        notaries = {
            "cra-notary": ("cra-civil", "cra", "cra-civil-relay"),
            "nia-notary": ("nia-population", "nia", "nia-population-relay"),
            "sro-notary": ("sro-social", "sro", "sro-social-relay"),
            "programme-notary": (
                "mosd-programme",
                "programme",
                "programme-mis-relay",
            ),
            "sipf-notary": ("sipf-pensions", "sipf", "sipf-pensions-relay"),
            "nagdi-notary": (
                "nagdi-agriculture",
                "nagdi",
                "nagdi-agriculture-relay",
            ),
        }
        local = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        services = local["services"]
        declared_volumes = set((local.get("volumes") or {}).keys())
        self.assertNotIn("redis", services)
        self.assertIn("postgres-data", declared_volumes)
        self.assertIn(
            "postgres-data:/var/lib/postgresql/data",
            services["postgres"]["volumes"],
        )
        self.assertNotIn(
            "postgres-data:/var/lib/postgresql",
            services["postgres"]["volumes"],
        )
        state_proof = (ROOT / "scripts" / "notary_state_restart.py").read_text(
            encoding="utf-8"
        )
        for required in (
            "SELECT system_identifier FROM pg_control_system()",
            "validate_runtime_pgdata_mounts",
            'self.run_just("down")',
            'self.run_just("up")',
            "compare_snapshots(before, after)",
            'volume_labels.get("com.docker.compose.volume") != "postgres-data"',
        ):
            self.assertIn(required, state_proof)
        self.assertNotIn('run_just("reset")', state_proof)
        self.assertNotIn('run_just("restart")', state_proof)
        self.assertEqual(
            {name for name in services if name.endswith("-notary")},
            set(notaries),
        )
        self.assertEqual(
            services["postgres"]["environment"]["SOLMARA_NOTARY_DATABASES"].split(),
            ["cra", "nia", "sro", "programme", "sipf", "nagdi"],
        )
        self.assertEqual(
            services["postgres"]["environment"]["SOLMARA_RELAY_DATABASES"].split(),
            ["cra", "nia", "sro", "programme", "sipf", "nagdi"],
        )
        source_urls = {
            services["nia-population-relay"]["environment"]["SOLMARA_NIA_DATABASE_URL"],
            services["sipf-pensions-relay"]["environment"]["SOLMARA_SIPF_DATABASE_URL"],
        }
        self.assertEqual(
            source_urls,
            {"${SOLMARA_NIA_DATABASE_URL}", "${SOLMARA_SIPF_DATABASE_URL}"},
        )
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn(
            "SOLMARA_NIA_DATABASE_URL=postgres://solmara_source_nia_reader:",
            env_example,
        )
        self.assertIn(
            "SOLMARA_SIPF_DATABASE_URL=postgres://solmara_source_sipf_reader:",
            env_example,
        )
        self.assertNotIn(
            "SOLMARA_NIA_DATABASE_URL=postgres://solmara_registry:", env_example
        )
        self.assertNotIn(
            "SOLMARA_SIPF_DATABASE_URL=postgres://solmara_registry:", env_example
        )
        for token_name in (
            "CRA_CHILD_BENEFIT_CLIENT_TOKEN",
            "NIA_CHILD_BENEFIT_CLIENT_TOKEN",
            "SRO_CHILD_BENEFIT_CLIENT_TOKEN",
            "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN",
        ):
            self.assertIn(f"{token_name}=", env_example)
        self.assertNotIn("CIVIL_CHILD_BENEFIT_NOTARY_TOKEN=", env_example)
        self.assertNotIn("NIA_CHILD_BENEFIT_NOTARY_TOKEN=", env_example)
        self.assertNotIn("SRO_CHILD_BENEFIT_NOTARY_TOKEN=", env_example)
        self.assertNotIn("PROGRAMME_CHILD_BENEFIT_NOTARY_TOKEN=", env_example)
        bootstrap = services["registry-postgresql-bootstrap"]
        self.assertEqual(bootstrap["restart"], "no")
        self.assertEqual(
            bootstrap["depends_on"]["postgres"]["condition"],
            "service_healthy",
        )

        runtime_urls = set()
        migrator_urls = set()
        relay_urls = set()
        for service_name, (project, database_key, relay_name) in notaries.items():
            with self.subTest(notary=service_name):
                config = yaml.safe_load(
                    (
                        ROOT
                        / "runtime"
                        / "registry-projects"
                        / "local"
                        / project
                        / "notary"
                        / "notary.yaml"
                    ).read_text(encoding="utf-8")
                )
                state = config["state"]
                self.assertEqual(state["storage"], "postgresql")
                self.assertEqual(
                    state["postgresql"]["url_env"], "REGISTRY_NOTARY_POSTGRES_URL"
                )
                self.assertEqual(
                    state["postgresql"]["root_certificate_path"],
                    "/etc/solmara/postgres/root.crt",
                )
                self.assertNotIn("replay", config)

                expected_database = f"solmara_notary_{database_key}"
                expected_runtime = f"{expected_database}_runtime"
                expected_migrator = f"{expected_database}_migrator"
                expected_owner = f"{expected_database}_owner"
                installer_name = f"{service_name}-state-install"
                workload_agent = f"{database_key}-workload-agent"

                runtime = services[service_name]
                installer = services[installer_name]
                agent = services[workload_agent]
                runtime_url = runtime["environment"]["REGISTRY_NOTARY_POSTGRES_URL"]
                migrator_url = installer["environment"][
                    "REGISTRY_NOTARY_POSTGRES_MIGRATOR_URL"
                ]
                relay_url = services[relay_name]["environment"][
                    "REGISTRY_RELAY_CONSULTATION_DATABASE_URL"
                ]
                relay_cache = f"{database_key}-relay-cache"
                self.assertIn(relay_cache, declared_volumes)
                self.assertIn(
                    f"{relay_cache}:/var/lib/registry-relay/cache",
                    services[relay_name]["volumes"],
                )
                self.assertIn(f"{expected_runtime}:", runtime_url)
                self.assertIn(f"/{expected_database}?sslmode=require", runtime_url)
                self.assertNotIn(
                    "REGISTRY_NOTARY_POSTGRES_MIGRATOR_URL", runtime["environment"]
                )
                self.assertIn(f"{expected_migrator}:", migrator_url)
                self.assertIn(f"/{expected_database}?sslmode=require", migrator_url)
                self.assertIn(expected_owner, installer["command"])
                self.assertIn(expected_runtime, installer["command"])
                self.assertEqual(installer["restart"], "no")
                self.assertEqual(runtime["network_mode"], f"service:{relay_name}")
                self.assertEqual(runtime["user"], "65534:65534")
                self.assertEqual(
                    runtime["healthcheck"]["test"],
                    [
                        "CMD",
                        "/usr/local/bin/registry-notary",
                        "healthcheck",
                        "--url",
                        "http://127.0.0.1:8081/ready",
                    ],
                )
                self.assertEqual(agent["network_mode"], f"service:{relay_name}")
                self.assertEqual(
                    installer["depends_on"]["registry-postgresql-bootstrap"][
                        "condition"
                    ],
                    "service_completed_successfully",
                )
                self.assertEqual(
                    installer["depends_on"][workload_agent]["condition"],
                    "service_healthy",
                )
                self.assertEqual(
                    runtime["depends_on"][installer_name]["condition"],
                    "service_completed_successfully",
                )
                self.assertEqual(
                    runtime["depends_on"][workload_agent]["condition"],
                    "service_healthy",
                )

                runtime_urls.add(runtime_url)
                migrator_urls.add(migrator_url)
                relay_urls.add(relay_url)

        self.assertEqual(len(runtime_urls), len(notaries))
        self.assertEqual(len(migrator_urls), len(notaries))
        self.assertEqual(len(relay_urls), len(notaries))

        esignet = yaml.safe_load(
            (ROOT / "compose.coolify.esignet.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("esignet-redis", esignet["services"])

    def test_hosted_child_benefit_topology_is_source_owned(self) -> None:
        core = yaml.safe_load(
            (ROOT / "compose.coolify.yaml").read_text(encoding="utf-8")
        )
        core_services = core["services"]
        self.assertIn("child-benefit-federator", core_services)
        self.assertNotIn("child-benefit-notary", core_services)
        federator = core_services["child-benefit-federator"]
        federator_env = federator["environment"]
        self.assertEqual(
            federator["labels"]["solmara.lab.host"],
            "child-benefit-federator.solmara.registrystack.org",
        )

        expected = (
            (
                "compose.coolify.interior.yaml",
                "cra-notary",
                "cra-civil-relay",
                "cra-civil",
                "CRA_NOTARY_URL",
                "CRA_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                {"birth-is-registered", "child-age-under-5"},
            ),
            (
                "compose.coolify.interior.yaml",
                "nia-notary",
                "nia-population-relay",
                "nia-population",
                "NIA_NOTARY_URL",
                "NIA_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                {"population-record-active"},
            ),
            (
                "compose.coolify.social-development.yaml",
                "sro-notary",
                "sro-social-relay",
                "sro-social",
                "SRO_NOTARY_URL",
                "SRO_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                {"household-below-poverty-threshold"},
            ),
            (
                "compose.coolify.social-development.yaml",
                "programme-notary",
                "programme-mis-relay",
                "mosd-programme",
                "PROGRAMME_NOTARY_URL",
                "PROGRAMME_CHILD_BENEFIT_CLIENT_TOKEN_HASH",
                {"not-already-enrolled"},
            ),
        )
        for (
            compose_name,
            service_id,
            relay_id,
            project,
            url_env,
            token_hash_env,
            expected_claims,
        ) in expected:
            with self.subTest(service=service_id):
                compose = yaml.safe_load(
                    (ROOT / compose_name).read_text(encoding="utf-8")
                )
                services = compose["services"]
                self.assertNotIn("child-benefit-notary", services)
                service = services[service_id]
                self.assertEqual(
                    service["network_mode"],
                    f"service:{relay_id}",
                )
                self.assertEqual(
                    service["labels"]["solmara.lab.host"],
                    f"{service_id}.solmara.registrystack.org",
                )
                self.assertIn(token_hash_env, service["environment"])

                public_url = f"https://{service_id}.solmara.registrystack.org"
                self.assertEqual(federator_env[url_env], public_url)
                config = yaml.safe_load(
                    (
                        ROOT
                        / "runtime"
                        / "registry-projects"
                        / "hosted"
                        / project
                        / "notary"
                        / "notary.yaml"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(config["instance"]["id"], service_id)
                self.assertEqual(config["evidence"]["service_id"], service_id)
                self.assertEqual(
                    config["evidence"]["relay"]["base_url"],
                    "http://127.0.0.1:8080",
                )
                self.assertTrue(
                    config["evidence"]["relay"]["allow_insecure_localhost"]
                )
                self.assertEqual(
                    config["evidence"]["relay"]["workload_client_id"], service_id
                )
                self.assertEqual(
                    config["evidence"]["relay"]["token_file"],
                    f"/run/secrets/{service_id}-relay-token",
                )
                self.assertEqual(
                    {
                        claim["id"]
                        for claim in config["evidence"]["claims"]
                        if claim["purpose"]
                        == "https://id.registrystack.org/solmara/purpose/child-benefit-review"
                    },
                    expected_claims,
                )

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
            smoke_live.catalog_claim_ids(
                {"data": [{"id": "person-is-deceased"}, {"id": "survivor-is-eligible"}]}
            ),
            {"person-is-deceased", "survivor-is-eligible"},
        )

    def test_live_smoke_waits_for_notary_readiness(self) -> None:
        smoke_live = load_smoke_live()
        urls: list[str] = []
        original_http_json = smoke_live.http_json

        def ready(method, url, headers, *, timeout):
            urls.append(url)
            return SimpleNamespace(status=200, error="")

        smoke_live.http_json = ready
        try:
            self.assertIsNone(
                smoke_live.wait_for_readiness("http://notary.test", "Test Notary")
            )
        finally:
            smoke_live.http_json = original_http_json

        self.assertEqual(urls, ["http://notary.test/ready"])

    def test_child_benefit_offerings_advertise_only_the_endpoint_purpose(self) -> None:
        expected_purposes = [
            "https://id.registrystack.org/solmara/purpose/child-benefit-review"
        ]
        offering_ids = (
            "cra-birth-registration-offering",
            "nia-population-population-status-offering",
            "sro-social-household-poverty-offering",
            "mosd-programme-beneficiary-enrollment-offering",
        )

        for offering_id in offering_ids:
            with self.subTest(offering=offering_id):
                path = (
                    ROOT
                    / "metadata"
                    / "public"
                    / "metadata"
                    / "evidence-offerings"
                    / f"{offering_id}.json"
                )
                offering = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(offering["purposes"], expected_purposes)

    def test_child_benefit_authority_predicate_collection_is_publicly_discoverable(
        self,
    ) -> None:
        catalog_path = ROOT / "metadata" / "public" / "metadata" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        services = {service["id"]: service for service in catalog["data_services"]}
        collector = services["child-benefit-evidence-collector-api"]

        self.assertEqual(
            collector["endpoint_url"],
            "https://child-benefit-federator.solmara.registrystack.org/v1/evaluations",
        )
        child_service = next(
            service
            for service in catalog["public_services"]
            if service["id"] == "child-benefit-review"
        )
        self.assertIn(
            "child-benefit-evidence-collector-api", child_service["data_services"]
        )

        offering_path = (
            ROOT
            / "metadata"
            / "public"
            / "metadata"
            / "evidence-offerings"
            / "solmara.child-benefit.authority-predicate-collection.json"
        )
        offering = json.loads(offering_path.read_text(encoding="utf-8"))
        self.assertEqual(
            offering["access"]["endpoint_url"],
            "https://child-benefit-federator.solmara.registrystack.org/v1/evaluations",
        )
        self.assertEqual(
            offering["access"]["media_type"],
            "application/json",
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
            ROOT
            / "requests"
            / "registry-lab"
            / "20 - Child Benefit"
            / "01 - Collect source predicates.bru",
            ROOT
            / "requests"
            / "registry-lab"
            / "30 - Pension Survivor"
            / "01 - Evaluate pension stop.bru",
            ROOT
            / "requests"
            / "registry-lab"
            / "30 - Pension Survivor"
            / "02 - Read active pension payment.bru",
            ROOT
            / "requests"
            / "registry-lab"
            / "30 - Pension Survivor"
            / "03 - Read survivor eligibility.bru",
            ROOT
            / "requests"
            / "registry-lab"
            / "40 - NAgDI Voucher"
            / "01 - Voucher eligibility.bru",
            ROOT
            / "requests"
            / "registry-lab"
            / "40 - NAgDI Voucher"
            / "02 - Livestock movement control.bru",
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
