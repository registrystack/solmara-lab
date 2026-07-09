from __future__ import annotations

import importlib.util
import subprocess
import sys
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
                "child-benefit-notary": [
                    "child-benefit-notary-state:/var/lib/registry-notary/config-state",
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
                    {"claim_id": "eligible-for-child-benefit", "value": True},
                    {"claim_id": "not-already-enrolled", "satisfied": False},
                ]
            }
        )

        self.assertEqual(
            values,
            {"eligible-for-child-benefit": True, "not-already-enrolled": False},
        )

    def test_live_smoke_extracts_catalog_claim_ids(self) -> None:
        smoke_live = load_smoke_live()

        self.assertEqual(
            smoke_live.catalog_claim_ids({"data": [{"id": "person-is-deceased"}, {"id": "survivor-is-eligible"}]}),
            {"person-is-deceased", "survivor-is-eligible"},
        )

    def test_compose_project_name_is_stable_and_checkout_scoped(self) -> None:
        compose_names = load_compose_project_name()

        first = compose_names.compose_project_name(Path("/tmp/solmara-lab"))
        second = compose_names.compose_project_name(Path("/tmp/other/solmara-lab"))

        self.assertRegex(first, r"^solmara-lab-[0-9a-f]{10}$")
        self.assertNotEqual(first, second)

    def test_notary_bru_requests_match_configured_auth_and_disclosure(self) -> None:
        requests = [
            ROOT / "requests" / "registry-lab" / "20 - Child Benefit" / "01 - Evaluate eligibility.bru",
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
