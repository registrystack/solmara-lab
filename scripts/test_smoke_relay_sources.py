from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-relay-sources.py"
SPEC = importlib.util.spec_from_file_location("smoke_relay_sources", SCRIPT)
smoke_relay_sources = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["smoke_relay_sources"] = smoke_relay_sources
SPEC.loader.exec_module(smoke_relay_sources)


class RelaySourceSmokeTests(unittest.TestCase):
    def test_accepts_the_missing_credential_problem_for_an_anonymous_request(
        self,
    ) -> None:
        response = (
            401,
            {"content-type": "application/problem+json"},
            {"code": "auth.missing_credential"},
            "",
        )

        self.assertIsNone(
            smoke_relay_sources.validate_unauthenticated_denial(response)
        )

    def test_rejects_the_invalid_credential_problem_when_no_token_was_sent(
        self,
    ) -> None:
        response = (
            401,
            {"content-type": "application/problem+json"},
            {"code": "auth.invalid_credentials"},
            "",
        )

        self.assertEqual(
            smoke_relay_sources.validate_unauthenticated_denial(response),
            "expected auth.missing_credential, got 'auth.invalid_credentials'",
        )

    def test_rejects_source_shaped_data_in_the_denial(self) -> None:
        response = (
            401,
            {"content-type": "application/problem+json; charset=utf-8"},
            {
                "code": "auth.missing_credential",
                "source_record": {"uin": "must-not-be-returned"},
            },
            "",
        )

        self.assertEqual(
            smoke_relay_sources.validate_unauthenticated_denial(response),
            "unauthenticated denial included source-shaped data",
        )


if __name__ == "__main__":
    unittest.main()
