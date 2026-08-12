from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("local-transit-signers.py")
SPEC = importlib.util.spec_from_file_location("local_transit_signers", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LocalTransitSignerOrchestrationTests(unittest.TestCase):
    def test_exact_provider_and_key_inventory(self) -> None:
        self.assertEqual(
            MODULE.PROVIDERS,
            ("mint", "cra", "nia", "sro", "mosd-programme", "sipf", "nagdi"),
        )
        self.assertEqual(MODULE.key_name("mint"), "solmara-mint")
        for provider in MODULE.PROVIDERS[1:]:
            self.assertEqual(MODULE.key_name(provider), f"solmara-evidence-{provider}")
            private_jwk, socket_path, _ = MODULE.paths(provider)
            self.assertEqual(private_jwk.name, "signing.jwk")
            self.assertEqual(socket_path.name, "transit-proxy.sock")

    def test_stop_never_claims_an_unrelated_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "unrelated.pid"
            pid_file.write_text(f"{os.getpid()}\n", encoding="ascii")
            self.assertIsNone(MODULE.owned_process(pid_file))


if __name__ == "__main__":
    unittest.main()
