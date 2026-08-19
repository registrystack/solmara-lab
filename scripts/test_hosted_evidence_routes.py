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
    "cra-evidence": (
        ROOT / "compose.coolify.interior.yaml",
        "SOLMARA_CRA_EVIDENCE_PUBLIC_HOST",
        "cra-evidence.solmara.registrystack.org",
    ),
    "nia-evidence": (
        ROOT / "compose.coolify.interior.yaml",
        "SOLMARA_NIA_EVIDENCE_PUBLIC_HOST",
        "nia-evidence.solmara.registrystack.org",
    ),
    "sro-evidence": (
        ROOT / "compose.coolify.social-development.yaml",
        "SOLMARA_SRO_EVIDENCE_PUBLIC_HOST",
        "sro-evidence.solmara.registrystack.org",
    ),
    "mosd-programme-evidence": (
        ROOT / "compose.coolify.social-development.yaml",
        "SOLMARA_MOSD_PROGRAMME_EVIDENCE_PUBLIC_HOST",
        "mosd-programme-evidence.solmara.registrystack.org",
    ),
    "sipf-evidence": (
        ROOT / "compose.coolify.labour-pensions.yaml",
        "SOLMARA_SIPF_EVIDENCE_PUBLIC_HOST",
        "sipf-evidence.solmara.registrystack.org",
    ),
    "nagdi-evidence": (
        ROOT / "compose.coolify.agriculture.yaml",
        "SOLMARA_NAGDI_EVIDENCE_PUBLIC_HOST",
        "nagdi-evidence.solmara.registrystack.org",
    ),
}

RELAY_ROUTES = {
    "cra-relay": (
        ROOT / "compose.coolify.interior.yaml",
        "cra-relay-authority-cells.solmara.registrystack.org",
    ),
    "nia-relay": (
        ROOT / "compose.coolify.interior.yaml",
        "nia-relay-authority-cells.solmara.registrystack.org",
    ),
    "mosd-relay": (
        ROOT / "compose.coolify.social-development.yaml",
        "mosd-programme-relay-authority-cells.solmara.registrystack.org",
    ),
    "sipf-relay": (
        ROOT / "compose.coolify.labour-pensions.yaml",
        "sipf-relay-authority-cells.solmara.registrystack.org",
    ),
    "nagdi-relay": (
        ROOT / "compose.coolify.agriculture.yaml",
        "nagdi-relay-authority-cells.solmara.registrystack.org",
    ),
}


def compose_environment() -> dict[str, str]:
    environment = os.environ | {
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
        overrides = {
            variable: f"{service}.staging.example.org"
            for service, (_, variable, _) in EVIDENCE_ROUTES.items()
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


if __name__ == "__main__":
    unittest.main()
