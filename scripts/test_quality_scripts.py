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


if __name__ == "__main__":
    unittest.main()
