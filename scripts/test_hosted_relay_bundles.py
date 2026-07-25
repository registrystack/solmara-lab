from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_hosted_relay_bundles",
        ROOT / "scripts" / "check-hosted-relay-bundles.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load check-hosted-relay-bundles.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_hosted_relay_bundles"] = module
    spec.loader.exec_module(module)
    return module


class HostedRelayBundleTests(unittest.TestCase):
    def test_artifact_closure_accepts_identical_complete_trees(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundled = root / "bundled"
            source = root / "source"
            for directory in (bundled, source):
                (directory / "contracts").mkdir(parents=True)
                (directory / "contracts" / "contract.json").write_text(
                    '{"version":1}\n', encoding="utf-8"
                )

            checker.verify_artifact_closure("example", bundled, source)

    def test_artifact_closure_rejects_changed_or_missing_files(self) -> None:
        checker = load_checker()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bundled = root / "bundled"
            source = root / "source"
            bundled.mkdir()
            source.mkdir()
            (bundled / "contract.json").write_text("signed", encoding="utf-8")
            (source / "contract.json").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(
                SystemExit, "signed artifact contract.json differs"
            ):
                checker.verify_artifact_closure("example", bundled, source)

            (source / "extra.json").write_text("extra", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "artifact paths differ"):
                checker.verify_artifact_closure("example", bundled, source)


if __name__ == "__main__":
    unittest.main()
