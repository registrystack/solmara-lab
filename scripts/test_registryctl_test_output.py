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
                        "requirements": [
                            {
                                "state": "covered",
                                "requirement": MODULE.REQUEST_BINDING_REQUIREMENT,
                                "evidence": [
                                    {
                                        "kind": "authored_fixture",
                                        "id": "target/example/fixture/match",
                                    }
                                ],
                            }
                        ]
                    }
                ]
            },
        }
        report.update(overrides)
        return json.dumps(report).encode("utf-8")

    def test_accepts_passing_authored_request_witnesses(self) -> None:
        self.assertEqual(
            MODULE.validate_test_report(self.report()),
            ("example", 1, 1),
        )

    def test_rejects_mapping_derived_request_coverage(self) -> None:
        coverage = {
            "targets": [
                {
                    "requirements": [
                        {
                            "state": "missing",
                            "requirement": MODULE.REQUEST_BINDING_REQUIREMENT,
                            "reason": "required_evidence_missing",
                            "evidence": [],
                        }
                    ]
                }
            ]
        }
        with self.assertRaisesRegex(
            MODULE.TestReportError,
            "every fixture target must cover",
        ):
            MODULE.validate_test_report(
                self.report(fixture_coverage=coverage)
            )

    def test_rejects_non_authored_binding_evidence(self) -> None:
        coverage = {
            "targets": [
                {
                    "requirements": [
                        {
                            "state": "covered",
                            "requirement": MODULE.REQUEST_BINDING_REQUIREMENT,
                            "evidence": [{"kind": "compiled_contract"}],
                        }
                    ]
                }
            ]
        }
        with self.assertRaisesRegex(
            MODULE.TestReportError,
            "requires authored fixture evidence",
        ):
            MODULE.validate_test_report(
                self.report(fixture_coverage=coverage)
            )

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
