from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "compose.coolify.esignet.yaml"
CORE_COMPOSE_PATH = ROOT / "compose.coolify.yaml"
RENDERER = ROOT / "docker" / "esignet-ui" / "render-hosted-nginx.sh"
TEMPLATE = ROOT / "config" / "esignet" / "nginx-hosted.conf"
LOCAL_COMPOSE_PATH = ROOT / "compose.esignet.yaml"
LOCAL_TEMPLATE = ROOT / "config" / "esignet" / "nginx.conf"


class HostedEsignetTopologyTests(unittest.TestCase):
    def test_mint_and_relay_dependency_origins_are_not_operator_overridable(
        self,
    ) -> None:
        compose_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (CORE_COMPOSE_PATH, COMPOSE_PATH)
        )
        for variable in (
            "SOLMARA_MINT_PUBLIC_BASE_URL",
            "SOLMARA_MINT_PUBLIC_HOST",
            "SOLMARA_CRA_RELAY_PUBLIC_BASE_URL",
            "SOLMARA_NIA_RELAY_PUBLIC_BASE_URL",
            "SOLMARA_MOSD_RELAY_PUBLIC_BASE_URL",
            "SOLMARA_SIPF_RELAY_PUBLIC_BASE_URL",
            "SOLMARA_NAGDI_RELAY_PUBLIC_BASE_URL",
        ):
            self.assertNotIn(variable, compose_text)

    def test_compose_is_a_standalone_esignet_app(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        services = compose["services"]
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
        # The issuer origin is fronted by the proxy image, not by eSignet
        # itself, so its discovery documents are reachable where the issuer
        # says they are.
        self.assertEqual(services["esignet_edge"]["image"], services["esignet_ui"]["image"])
        self.assertNotIn("solmara.lab.host", services["esignet"]["labels"])
        self.assertNotIn("portal", services)
        self.assertEqual(
            services["esignet"]["environment"]["REGISTRY_MINT_TOKEN_ENDPOINT"],
            "https://mint-authority-cells.solmara.registrystack.org/token",
        )
        self.assertEqual(
            services["esignet"]["environment"]["REGISTRY_RELAY_BASE_URL"],
            "https://nia-relay-authority-cells.solmara.registrystack.org",
        )
        self.assertEqual(
            services["esignet-seed"]["environment"][
                "ESIGNET_CLIENT_REDIRECT_URIS_JSON"
            ],
            '["${SOLMARA_PORTAL_PUBLIC_BASE_URL:-https://portal.solmara.registrystack.org}/auth/callback"]',
        )

    def test_renderer_accepts_only_dns_hosts_and_preserves_security_headers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nginx.conf"
            environment = os.environ | {
                "SOLMARA_ESIGNET_PUBLIC_HOST": "login-authority-cells.example.org",
                "SOLMARA_ESIGNET_UI_PUBLIC_HOST": "login-ui-authority-cells.example.org",
            }
            subprocess.run(
                [str(RENDERER), str(TEMPLATE), str(output)],
                check=True,
                env=environment,
                capture_output=True,
                text=True,
            )
            rendered = output.read_text(encoding="utf-8")
            self.assertNotIn("__ESIGNET_", rendered)
            self.assertIn(
                "proxy_set_header Host login-authority-cells.example.org;", rendered
            )
            self.assertIn(
                "proxy_set_header X-Forwarded-Host login-authority-cells.example.org;",
                rendered,
            )
            self.assertIn("default-src 'none'", rendered)
            self.assertIn(
                "connect-src 'self' https://login-authority-cells.example.org https://login-ui-authority-cells.example.org;",
                rendered,
            )

    def test_renderer_rejects_directive_injection(self) -> None:
        invalid_hosts = (
            "login.example.org;return 200",
            "login.example.org/path",
            "login.example.org example.net",
            "UPPER.example.org",
            "localhost",
        )
        for invalid_host in invalid_hosts:
            with (
                self.subTest(invalid_host=invalid_host),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = subprocess.run(
                    [str(RENDERER), str(TEMPLATE), str(Path(directory) / "nginx.conf")],
                    env=os.environ
                    | {
                        "SOLMARA_ESIGNET_PUBLIC_HOST": invalid_host,
                        "SOLMARA_ESIGNET_UI_PUBLIC_HOST": "ui.example.org",
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 78)
                self.assertEqual(
                    result.stderr,
                    "eSignet hosted nginx host configuration is invalid\n",
                )
                self.assertNotIn(invalid_host, result.stderr)

    def test_renderer_passes_through_a_template_without_host_placeholders(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in ("SOLMARA_ESIGNET_PUBLIC_HOST", "SOLMARA_ESIGNET_UI_PUBLIC_HOST")
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nginx.conf"
            result = subprocess.run(
                [str(RENDERER), str(LOCAL_TEMPLATE), str(output)],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                LOCAL_TEMPLATE.read_text(encoding="utf-8"),
            )

    def test_renderer_rejects_absent_hosts_when_the_template_has_placeholders(
        self,
    ) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            not in ("SOLMARA_ESIGNET_PUBLIC_HOST", "SOLMARA_ESIGNET_UI_PUBLIC_HOST")
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [
                    str(RENDERER),
                    str(TEMPLATE),
                    str(Path(temporary_directory) / "nginx.conf"),
                ],
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 78)
            self.assertEqual(
                result.stderr,
                "eSignet hosted nginx host configuration is invalid\n",
            )

    def test_local_esignet_ui_services_build_a_placeholder_free_template(self) -> None:
        compose = yaml.safe_load(LOCAL_COMPOSE_PATH.read_text(encoding="utf-8"))
        services = compose["services"]
        for name in ("esignet-ui", "esignet-edge"):
            with self.subTest(service=name):
                template = ROOT / services[name]["build"]["args"]["ESIGNET_NGINX_CONF"]
                self.assertNotIn(
                    "__ESIGNET_", template.read_text(encoding="utf-8")
                )


if __name__ == "__main__":
    unittest.main()
