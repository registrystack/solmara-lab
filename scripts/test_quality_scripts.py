from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


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
