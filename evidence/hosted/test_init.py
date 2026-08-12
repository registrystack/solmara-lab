from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("init.py")
SPEC = importlib.util.spec_from_file_location("hosted_evidence_init", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load hosted Evidence initializer")
INITIALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INITIALIZER)


def private_jwk(kid: str, x: str) -> dict[str, str]:
    return {"alg": "ES256", "crv": "P-256", "d": "private", "kid": kid, "kty": "EC", "x": x, "y": f"{x}-y"}


class HostedEvidenceInitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        local = "\n".join(
            [
                "authentication:",
                "assuranceProfile: local",
                "  issuer: https://mint.evidence.solmara.invalid",
                "signing:",
                "  activePublicJwkFile: public-keys/local.jwk.json",
                "sources:",
                *[
                    f"  source-{index}:\n    baseUrl: {url}\n    tlsTrustProfile: solmara-lab\n    authentication: {{ kind: static-bearer, tokenRef: {token} }}"
                    for index, (url, token) in enumerate(
                        [
                            ("https://cra-relay.evidence.solmara.invalid", "secret:file/cra-relay-token"),
                            ("https://nia-relay.evidence.solmara.invalid", "secret:file/nia-relay-token"),
                            ("https://sro-relay.evidence.solmara.invalid", "secret:file/sro-relay-token"),
                            ("https://programme-relay.evidence.solmara.invalid", "secret:file/programme-relay-token"),
                            ("https://sipf-relay.evidence.solmara.invalid", "secret:file/sipf-relay-token"),
                            ("https://nagdi-relay.evidence.solmara.invalid", "secret:file/nagdi-relay-token"),
                        ]
                    )
                ],
            ]
        )
        (self.source / "evidence.yaml").write_text(local + "\n", encoding="utf-8")
        (self.source / "adapter.rhai").write_text("#{ facts: #{} }\n", encoding="utf-8")
        self.environment = {
            "EVIDENCE_AUDIT_HMAC_KEY": "a" * 32,
            "EVIDENCE_SUBJECT_BINDING_HMAC_KEY": "b" * 32,
            "EVIDENCE_SIGNING_PUBLIC_JWK": json.dumps({key: value for key, value in private_jwk("evidence", "e").items() if key != "d"}),
            "MINT_AUDIT_HMAC_KEY": "c" * 32,
            "MINT_SIGNING_PUBLIC_JWK": json.dumps({key: value for key, value in private_jwk("mint", "m").items() if key != "d"}),
            "SOLMARA_EVIDENCE_CLIENT_JWK": json.dumps(private_jwk("client", "x")),
            "SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK": json.dumps(
                {"alg": "ES256", "crv": "P-256", "kid": "client", "kty": "EC", "x": "x", "y": "x-y"}
            ),
        }
        self.args = argparse.Namespace(
            bundle_source=self.source,
            bundle_target=self.root / "bundle",
            evidence_secrets=self.root / "evidence-secrets",
            mint_secrets=self.root / "mint-secrets",
            application_secrets=self.root / "application-secrets",
            mint_clients=self.root / "clients",
            mint_public_keys=self.root / "mint-public-keys",
            evidence_audit=self.root / "evidence-audit",
            mint_audit=self.root / "mint-audit",
            uid=os.getuid(),
            gid=os.getgid(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initializes_private_files_and_exact_public_endpoints(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            INITIALIZER.initialize(self.args)

        config = (self.args.bundle_target / "evidence.yaml").read_text(encoding="utf-8")
        self.assertNotIn(".solmara.invalid", config)
        self.assertNotIn("tlsTrustProfile", config)
        self.assertIn("https://mosd-programme-relay.solmara.registrystack.org", config)
        self.assertIn("secret:file/relay/cra/cra-relay-token", config)
        self.assertIn("assuranceProfile: production", config)
        client = json.loads((self.args.mint_clients / "solmara-demo.yaml").read_text())
        self.assertNotIn("d", client["keys"][0])
        mode = stat_mode(self.args.application_secrets / "solmara-evidence-client.jwk")
        self.assertEqual(mode, 0o600)
        self.assertNotIn("d", json.loads((self.args.mint_public_keys / "active.jwk.json").read_text()))

    def test_rejects_public_client_jwk_with_private_member(self) -> None:
        self.environment["SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK"] = self.environment[
            "SOLMARA_EVIDENCE_CLIENT_JWK"
        ]
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(ValueError, "must not contain private"):
                INITIALIZER.initialize(self.args)

    def test_rejects_mismatched_client_key_pair(self) -> None:
        public = json.loads(self.environment["SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK"])
        public["x"] = "different"
        self.environment["SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK"] = json.dumps(public)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(ValueError, "does not match"):
                INITIALIZER.initialize(self.args)

    def test_rejects_mismatched_client_y_coordinate(self) -> None:
        public = json.loads(self.environment["SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK"])
        public["y"] = "different"
        self.environment["SOLMARA_EVIDENCE_CLIENT_PUBLIC_JWK"] = json.dumps(public)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(ValueError, "does not match"):
                INITIALIZER.initialize(self.args)

    def test_refuses_to_replace_stable_security_keys(self) -> None:
        with mock.patch.dict(os.environ, self.environment, clear=True):
            INITIALIZER.initialize(self.args)

        changed = dict(self.environment)
        changed["EVIDENCE_AUDIT_HMAC_KEY"] = "z" * 32
        with mock.patch.dict(os.environ, changed, clear=True):
            with self.assertRaisesRegex(ValueError, "refusing to replace stable secret"):
                INITIALIZER.initialize(self.args)

        self.assertEqual(
            (self.args.evidence_secrets / "audit-hmac-key").read_text(),
            "a" * 32 + "\n",
        )


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
