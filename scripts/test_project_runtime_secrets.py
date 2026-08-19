from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("project-runtime-secrets.py")
SPEC = importlib.util.spec_from_file_location("secret_projection", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RuntimeSecretProjectionTests(unittest.TestCase):
    def test_signing_keys_never_enter_runtime_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private, output = root / "private", root / "runtime"
            for cell, clients in MODULE.CELL_CLIENTS.items():
                secrets = private / cell / "secrets"
                secrets.mkdir(parents=True)
                client_files = tuple(f"{client}-{suffix}" for client in clients for suffix in ("client-id", "client-key"))
                for name in ("signing.jwk", "audit-hmac-key", "subject-binding-hmac-key", *client_files):
                    (secrets / name).write_text(name)
            mint = private / "mint/secrets"
            mint.mkdir(parents=True)
            (mint / "signing.jwk").write_text("private")
            (mint / "audit-hmac-key").write_text("audit")
            MODULE.project(private, output)
            self.assertFalse(list(output.rglob("signing.jwk")))
            self.assertTrue((output / "cra/cra-pension-evidence-client-key").exists())
            self.assertEqual(
                (output / "cra/cra-pension-evidence-client-id").read_text(),
                "cra-pension-evidence-client-id",
            )
            self.assertEqual((output / "mint/audit-hmac-key").read_text(), "audit")
            for path in output.glob("*/*"):
                metadata = path.stat(follow_symlinks=False)
                self.assertTrue(stat.S_ISREG(metadata.st_mode), path)
                self.assertEqual(metadata.st_nlink, 1, path)
                self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600, path)


if __name__ == "__main__":
    unittest.main()
