from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TEST_IMAGE = "example.invalid/solmara@sha256:" + "a" * 64

EVIDENCE_ROUTES = {
    "cra_evidence": (
        ROOT / "compose.coolify.interior.yaml",
        "SOLMARA_CRA_EVIDENCE_PUBLIC_HOST",
        "cra-evidence.solmara.registrystack.org",
    ),
    "nia_evidence": (
        ROOT / "compose.coolify.interior.yaml",
        "SOLMARA_NIA_EVIDENCE_PUBLIC_HOST",
        "nia-evidence.solmara.registrystack.org",
    ),
    "sro_evidence": (
        ROOT / "compose.coolify.social-development.yaml",
        "SOLMARA_SRO_EVIDENCE_PUBLIC_HOST",
        "sro-evidence.solmara.registrystack.org",
    ),
    "mosd_programme_evidence": (
        ROOT / "compose.coolify.social-development.yaml",
        "SOLMARA_MOSD_PROGRAMME_EVIDENCE_PUBLIC_HOST",
        "mosd-programme-evidence.solmara.registrystack.org",
    ),
    "sipf_evidence": (
        ROOT / "compose.coolify.labour-pensions.yaml",
        "SOLMARA_SIPF_EVIDENCE_PUBLIC_HOST",
        "sipf-evidence.solmara.registrystack.org",
    ),
    "nagdi_evidence": (
        ROOT / "compose.coolify.agriculture.yaml",
        "SOLMARA_NAGDI_EVIDENCE_PUBLIC_HOST",
        "nagdi-evidence.solmara.registrystack.org",
    ),
}

RELAY_ROUTES = {
    "cra_relay": (
        ROOT / "compose.coolify.interior.yaml",
        "cra-relay-authority-cells.solmara.registrystack.org",
    ),
    "nia_relay": (
        ROOT / "compose.coolify.interior.yaml",
        "nia-relay-authority-cells.solmara.registrystack.org",
    ),
    "mosd_relay": (
        ROOT / "compose.coolify.social-development.yaml",
        "mosd-programme-relay-authority-cells.solmara.registrystack.org",
    ),
    "sipf_relay": (
        ROOT / "compose.coolify.labour-pensions.yaml",
        "sipf-relay-authority-cells.solmara.registrystack.org",
    ),
    "nagdi_relay": (
        ROOT / "compose.coolify.agriculture.yaml",
        "nagdi-relay-authority-cells.solmara.registrystack.org",
    ),
}


def compose_environment() -> dict[str, str]:
    environment = os.environ | {
        # Coolify exports this into the environment it runs Compose in, and the
        # routed services read it to name the network the ingress proxy is on.
        "COOLIFY_RESOURCE_UUID": "test-application-uuid",
        "SOLMARA_AUTHORITY_PROVISIONER_IMAGE": TEST_IMAGE,
        "REGISTRY_RELAY_IMAGE": TEST_IMAGE,
        "SOLMARA_EVIDENCE_IMAGE": TEST_IMAGE,
        "CRA_RELAY_AUDIT_KEY": "test",
        "NIA_RELAY_AUDIT_KEY": "test",
        "MOSD_RELAY_AUDIT_KEY": "test",
        "SIPF_RELAY_AUDIT_KEY": "test",
        "SIPF_RELAY_CURSOR_KEY": "test",
        "NAGDI_RELAY_AUDIT_KEY": "test",
        "NAGDI_RELAY_CURSOR_KEY": "test",
    }
    for _, variable, _ in EVIDENCE_ROUTES.values():
        environment.pop(variable, None)
    return environment


def render_compose(path: Path, overrides: dict[str, str] | None = None) -> dict:
    environment = compose_environment()
    environment.update(overrides or {})
    with tempfile.NamedTemporaryFile() as empty_env:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                empty_env.name,
                "-f",
                str(path),
                "config",
                "--format",
                "json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
    return json.loads(result.stdout)


class HostedEvidenceRouteTests(unittest.TestCase):
    def test_raw_compose_declares_canonical_evidence_defaults(self) -> None:
        for service, (path, variable, canonical_host) in EVIDENCE_ROUTES.items():
            with self.subTest(service=service):
                compose = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    compose["services"][service]["labels"]["solmara.lab.host"],
                    f"${{{variable}:-{canonical_host}}}",
                )

    def test_canonical_evidence_defaults_render_across_apps(self) -> None:
        rendered = {
            path: render_compose(path)
            for path in {route[0] for route in EVIDENCE_ROUTES.values()}
        }
        for service, (path, _, canonical_host) in EVIDENCE_ROUTES.items():
            with self.subTest(service=service):
                self.assertEqual(
                    rendered[path]["services"][service]["labels"]["solmara.lab.host"],
                    canonical_host,
                )

    def test_staging_evidence_hosts_render_without_changing_relay_routes(self) -> None:
        # The compose key is not a hostname label, so the staging host comes
        # from the canonical route rather than from the service name.
        overrides = {
            variable: f"{canonical_host.split('.', 1)[0]}.staging.example.org"
            for _, variable, canonical_host in EVIDENCE_ROUTES.values()
        }
        rendered = {
            path: render_compose(path, overrides)
            for path in {route[0] for route in EVIDENCE_ROUTES.values()}
        }
        for service, (path, variable, _) in EVIDENCE_ROUTES.items():
            with self.subTest(service=service):
                self.assertEqual(
                    rendered[path]["services"][service]["labels"]["solmara.lab.host"],
                    overrides[variable],
                )

        for service, (path, permanent_host) in RELAY_ROUTES.items():
            with self.subTest(service=service):
                self.assertEqual(
                    rendered[path]["services"][service]["labels"]["solmara.lab.host"],
                    permanent_host,
                )


class RoutedServiceNameTests(unittest.TestCase):
    def test_every_routed_service_carries_a_coolify_resolvable_name(self) -> None:
        """Coolify accepts a routed service only under its exact compose key but
        resolves it after rewriting "-" to "_", so a hyphenated key is stored
        where routing never reads it and the service answers no public route."""
        for path in sorted(ROOT.glob("compose.coolify*.yaml")):
            compose = yaml.safe_load(path.read_text(encoding="utf-8"))
            for name, service in (compose.get("services") or {}).items():
                labels = service.get("labels") or {}
                if "solmara.lab.host" not in labels:
                    continue
                with self.subTest(compose=path.name, service=name):
                    self.assertNotIn("-", name)


class EvidenceIdentityTests(unittest.TestCase):
    def test_every_cell_bundle_names_the_origin_it_is_routed_on(self) -> None:
        """`service.publicOrigin` is the resource identity RFC 9728 discovery
        answers with, so a bundle that names anything other than the cell's own
        canonical route hands a relying party the wrong resource."""
        for service, (_, _, canonical_host) in EVIDENCE_ROUTES.items():
            cell = service.removesuffix("_evidence").replace("_", "-")
            bundle = ROOT / "evidence" / "cells" / cell / "bundle" / "evidence.yaml"
            with self.subTest(cell=cell):
                config = yaml.safe_load(bundle.read_text(encoding="utf-8"))
                self.assertEqual(
                    config["service"]["publicOrigin"], f"https://{canonical_host}"
                )


if __name__ == "__main__":
    unittest.main()
