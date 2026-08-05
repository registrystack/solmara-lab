from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    compose_spec = importlib.util.spec_from_file_location(
        "compose_project_name", ROOT / "scripts/compose_project_name.py"
    )
    if compose_spec is None or compose_spec.loader is None:
        raise RuntimeError("could not load compose_project_name.py")
    compose_module = importlib.util.module_from_spec(compose_spec)
    sys.modules["compose_project_name"] = compose_module
    compose_spec.loader.exec_module(compose_module)

    spec = importlib.util.spec_from_file_location(
        "solmara_gen_secrets", ROOT / "scripts/gen-secrets.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load gen-secrets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EvidenceMaterialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = load_generator()

    def test_complete_material_is_preserved_across_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.generator.EVIDENCE_LOCAL_DIR = root
            self.generator.ensure_evidence_material()
            first = {
                path.relative_to(root): hashlib.sha256(path.read_bytes()).digest()
                for path in root.rglob("*")
                if path.is_file()
            }

            self.generator.ensure_evidence_material()
            second = {
                path.relative_to(root): hashlib.sha256(path.read_bytes()).digest()
                for path in root.rglob("*")
                if path.is_file()
            }

            self.assertEqual(first, second)
            self.assertEqual(len(first), 11)

    def test_partial_material_fails_without_rotating_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "evidence/audit-hmac-key"
            existing.parent.mkdir(parents=True)
            existing.write_text("existing-audit-key\n")
            self.generator.EVIDENCE_LOCAL_DIR = root

            with self.assertRaisesRegex(SystemExit, "incomplete local Evidence material"):
                self.generator.ensure_evidence_material()

            self.assertEqual(existing.read_text(), "existing-audit-key\n")


if __name__ == "__main__":
    unittest.main()
