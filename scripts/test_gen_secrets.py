from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

SCRIPT = Path(__file__).with_name("gen-secrets.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("gen_secrets", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SecretGenerationTests(unittest.TestCase):
    def test_p256_key_is_private_and_thumbprint_bound(self) -> None:
        jwk = json.loads(MODULE.p256_jwk())
        self.assertEqual((jwk["kty"], jwk["crv"], jwk["alg"]), ("EC", "P-256", "ES256"))
        self.assertIn("d", jwk)
        self.assertEqual(len(jwk["kid"]), 43)

    def test_rsa_key_is_private_and_thumbprint_bound(self) -> None:
        jwk = json.loads(MODULE.rsa_jwk())
        self.assertEqual((jwk["kty"], jwk["alg"]), ("RSA", "RS256"))
        self.assertEqual(set(jwk), {"kty", "alg", "n", "e", "d", "p", "q", "dp", "dq", "qi", "kid"})
        self.assertEqual(len(jwk["kid"]), 43)

    def test_operator_material_is_create_only_and_per_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            previous = MODULE.LOCAL
            MODULE.LOCAL = Path(temporary)
            try:
                first = MODULE.ensure_operator_material()
                signing = MODULE.LOCAL / "cells/cra/secrets/signing.jwk"
                before = signing.read_bytes()
                second = MODULE.ensure_operator_material()
                self.assertEqual(signing.read_bytes(), before)
                self.assertEqual(first, second)
                self.assertTrue((MODULE.LOCAL / "cells/nagdi/secrets/subject-binding-hmac-key").exists())
                client_id = MODULE.LOCAL / "cells/cra/secrets/cra-pension-evidence-client-id"
                self.assertEqual(client_id.read_bytes(), b"cra-pension-evidence")
                self.assertEqual(client_id.stat().st_mode & 0o777, 0o600)
                esignet_key = MODULE.LOCAL / "cells/mint/clients/nia-esignet-rsa-client-key"
                self.assertEqual(json.loads(esignet_key.read_text())["kty"], "RSA")
                self.assertEqual(esignet_key.stat().st_mode & 0o777, 0o600)
            finally:
                MODULE.LOCAL = previous

    def test_client_identifier_migrates_only_the_previous_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            client_id = Path(temporary) / "client-id"
            client_id.write_bytes(b"registered-client\n")
            MODULE.ensure_client_identifier(client_id, "registered-client")
            self.assertEqual(client_id.read_bytes(), b"registered-client")

            client_id.write_bytes(b"different-client")
            with self.assertRaises(ValueError):
                MODULE.ensure_client_identifier(client_id, "registered-client")
            self.assertEqual(client_id.read_bytes(), b"different-client")

    def test_generated_environment_preserves_runtime_secrets(self) -> None:
        existing = {
            key: f"stable-{index}"
            for index, key in enumerate(MODULE.RANDOM_ENV_KEYS)
        }
        existing["PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64"] = "stable-portal-key"
        operator = {
            "NIA_ESIGNET_CLIENT_PRIVATE_JWK": "operator-jwk",
            "SOLMARA_EVIDENCE_CLIENT_KEY": "/operator/client-key",
        }
        with (
            mock.patch.object(MODULE, "raw_key", side_effect=AssertionError("rotated")),
            mock.patch.object(
                MODULE,
                "rsa_private_key_b64",
                side_effect=AssertionError("rotated"),
            ),
        ):
            values = MODULE.compose_environment_values(existing, operator)
        for key, value in existing.items():
            self.assertEqual(values[key], value)
        self.assertEqual(values["NIA_ESIGNET_CLIENT_PRIVATE_JWK"], "operator-jwk")

    def test_generated_environment_rejects_duplicate_or_empty_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("KEY=value\nKEY=other\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                MODULE.load_environment(path)
            path.write_text("KEY=\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid"):
                MODULE.load_environment(path)
            path.write_text("KEY='unterminated\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "malformed"):
                MODULE.load_environment(path)


if __name__ == "__main__":
    unittest.main()
