from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-signer-public-keys.py")
SPEC = importlib.util.spec_from_file_location("signer_public_keys", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SignerPublicKeyTests(unittest.TestCase):
    def test_current_generated_signers_match(self) -> None:
        self.assertEqual(MODULE.failures(), [])

    def test_mismatch_fails_closed_without_private_value_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for provider in MODULE.PROVIDERS:
                private = {"alg": "ES256", "crv": "P-256", "kid": provider, "kty": "EC", "x": "x", "y": "y", "d": "private"}
                private_path = root / "config/evidence/local/cells" / provider / "secrets/signing.jwk"
                private_path.parent.mkdir(parents=True)
                private_path.write_text(json.dumps(private), encoding="utf-8")
                public_root = root / "runtime/evidence-cells/mint/public-keys" if provider == "mint" else root / "runtime/evidence-cells/cells" / provider / "bundle/public-keys"
                public_root.mkdir(parents=True)
                public = {name: private[name] for name in MODULE.PUBLIC_MEMBERS}
                if provider == "cra":
                    public["x"] = "different"
                (public_root / f"{provider}.jwk.json").write_text(json.dumps(public), encoding="utf-8")
            found = MODULE.failures(root)
            self.assertEqual(found, ["cra: generated public key does not match operator signer"])
            self.assertNotIn("private", " ".join(found))


if __name__ == "__main__":
    unittest.main()
