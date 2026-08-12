from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
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
            self.assertEqual(len(first), 17)

    def test_service_public_jwks_exclude_private_material_and_use_thumbprint_kids(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.generator.EVIDENCE_LOCAL_DIR = root
            self.generator.ensure_evidence_material()

            pairs = (
                (
                    root / "evidence/signing-p256-private-jwk",
                    root / "evidence/signing-p256-public.jwk",
                ),
                (
                    root / "mint/signing.jwk",
                    root / "mint/signing-public.jwk",
                ),
            )
            for private_path, public_path in pairs:
                private = json.loads(private_path.read_text())
                public = json.loads(public_path.read_text())
                thumbprint = json.dumps(
                    {
                        "crv": public["crv"],
                        "kty": public["kty"],
                        "x": public["x"],
                        "y": public["y"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
                expected_kid = (
                    base64.urlsafe_b64encode(hashlib.sha256(thumbprint).digest())
                    .rstrip(b"=")
                    .decode("ascii")
                )

                self.assertIn("d", private)
                self.assertNotIn("d", public)
                self.assertEqual(set(public), {"alg", "crv", "kid", "kty", "x", "y"})
                self.assertEqual(public["kid"], expected_kid)
                self.assertEqual(
                    public, self.generator.public_jwk(private_path.read_text())
                )
                self.assertEqual(private_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(public_path.stat().st_mode & 0o777, 0o644)
                rendered_config = private_path.parent / (
                    "evidence.yaml"
                    if private_path.parent.name == "evidence"
                    else "mint.yaml"
                )
                generated_public = (
                    private_path.parent / "public-keys" / f"{expected_kid}.jwk.json"
                )
                self.assertEqual(json.loads(generated_public.read_text()), public)
                self.assertIn(
                    f"public-keys/{expected_kid}.jwk.json",
                    rendered_config.read_text(),
                )
                self.assertNotIn("active.jwk.json", rendered_config.read_text())

    def test_partial_material_fails_without_rotating_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "evidence/audit-hmac-key"
            existing.parent.mkdir(parents=True)
            existing.write_text("existing-audit-key\n")
            self.generator.EVIDENCE_LOCAL_DIR = root

            with self.assertRaisesRegex(
                SystemExit, "incomplete local Evidence material"
            ):
                self.generator.ensure_evidence_material()

            self.assertEqual(existing.read_text(), "existing-audit-key\n")

    def test_private_key_jwt_client_keeps_its_exact_authority_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.generator.EVIDENCE_LOCAL_DIR = root
            self.generator.ensure_evidence_material()

            private = json.loads((root / "mint/client-private.jwk").read_text())
            client = json.loads((root / "mint/clients/solmara-demo.yaml").read_text())
            mint_config = (root / "mint/mint.yaml").read_text()
            evidence_config = (root / "evidence/evidence.yaml").read_text()

            self.assertEqual(private["alg"], "EdDSA")
            self.assertIn("d", private)
            self.assertNotIn("d", client["keys"][0])
            self.assertEqual(
                client["keys"], [self.generator.public_jwk(json.dumps(private))]
            )
            self.assertEqual(
                client["evidenceAudience"],
                "https://id.registrystack.org/solmara/audience/demo-client",
            )
            self.assertIn(
                "audience: https://mint.evidence.solmara.invalid/token", mint_config
            )
            self.assertIn("algorithms: [EdDSA]", mint_config)
            self.assertIn("audiences: [solmara-evidence]", mint_config)
            self.assertIn("audiences: [solmara-evidence]", evidence_config)

    def test_legacy_service_signing_keys_rotate_without_replacing_other_material(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.generator.EVIDENCE_LOCAL_DIR = root
            self.generator.ensure_evidence_material()
            preserved_paths = (
                root / "evidence/audit-hmac-key",
                root / "evidence/subject-binding-hmac-key",
                root / "mint/audit-hmac-key",
                root / "mint/client-private.jwk",
                root / "mint/clients/solmara-demo.yaml",
                root / "tls/ca.key",
                root / "tls/ca.crt",
                root / "tls/gateway.key",
                root / "tls/gateway.crt",
            )
            preserved = {
                path: hashlib.sha256(path.read_bytes()).digest()
                for path in preserved_paths
            }

            legacy_evidence = root / "evidence/signing-ed25519-private-jwk"
            self.generator.write_private(
                legacy_evidence,
                self.generator.local_ed25519_jwk("legacy-evidence"),
            )
            self.generator.write_private(
                root / "mint/signing.jwk",
                self.generator.local_ed25519_jwk("legacy-mint"),
            )
            for path in (
                root / "evidence/signing-p256-private-jwk",
                root / "evidence/signing-p256-public.jwk",
                root / "mint/signing-public.jwk",
            ):
                path.unlink()

            self.generator.ensure_evidence_material()

            self.assertFalse(legacy_evidence.exists())
            self.assertEqual(
                json.loads((root / "mint/signing.jwk").read_text())["alg"],
                "ES256",
            )
            self.assertEqual(
                {
                    path: hashlib.sha256(path.read_bytes()).digest()
                    for path in preserved_paths
                },
                preserved,
            )


if __name__ == "__main__":
    unittest.main()
