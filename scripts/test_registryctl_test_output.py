from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "registryctl_test_output",
    ROOT / "scripts" / "registryctl-test-output.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegistryctlTestOutputTests(unittest.TestCase):
    def report(self, **overrides: object) -> bytes:
        report: dict[str, object] = {
            "schema_version": MODULE.REPORT_SCHEMA,
            "status": "passed",
            "project": "example",
            "fixtures": [{"fixture": "match", "passed": True}],
            "fixture_coverage": {
                "targets": [
                    {
                        "identity": {"integration": "example", "capability": "snapshot"},
                        "fixture_set_state": "fixture_bearing",
                        "compiled_contract": {
                            "kind": "compiled_contract",
                            "digest": "sha256:compiled",
                        },
                        "fixture_inventory": [
                            {
                                "fixture_id": "match",
                                "fixture_digest": "sha256:fixture",
                                "pass_state": "passed",
                            }
                        ],
                    }
                ]
            },
        }
        report.update(overrides)
        return json.dumps(report).encode("utf-8")

    def test_accepts_passing_compiled_fixture_coverage(self) -> None:
        self.assertEqual(
            MODULE.validate_test_report(self.report()),
            ("example", 1, 1),
        )

    def test_rejects_a_target_without_a_compiled_contract(self) -> None:
        coverage = {"targets": [{"identity": {"integration": "example", "capability": "snapshot"}, "fixture_set_state": "fixture_bearing", "fixture_inventory": []}]}
        with self.assertRaisesRegex(
            MODULE.TestReportError,
            "must bind passing fixtures",
        ):
            MODULE.validate_test_report(self.report(fixture_coverage=coverage))

    def test_rejects_a_non_passing_coverage_fixture(self) -> None:
        report = json.loads(self.report())
        report["fixture_coverage"]["targets"][0]["fixture_inventory"][0]["pass_state"] = "failed"
        with self.assertRaisesRegex(
            MODULE.TestReportError,
            "must bind passing fixtures",
        ):
            MODULE.validate_test_report(json.dumps(report).encode())

    def test_rejects_a_non_passing_fixture_without_echoing_values(self) -> None:
        with self.assertRaisesRegex(
            MODULE.TestReportError,
            "non-passing fixture",
        ) as rejected:
            MODULE.validate_test_report(
                self.report(
                    fixtures=[
                        {
                            "fixture": "secret-fixture-name",
                            "passed": False,
                        }
                    ]
                )
            )
        self.assertNotIn("secret-fixture-name", str(rejected.exception))


if __name__ == "__main__":
    unittest.main()
