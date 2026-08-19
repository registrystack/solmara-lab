from __future__ import annotations

import importlib.util
import socket
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("check-local-transit-providers.py")
SPEC = importlib.util.spec_from_file_location("transit_check", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TransitProviderTests(unittest.TestCase):
    def test_missing_providers_fail_explicitly(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="s") as temporary:
            self.assertEqual(len(MODULE.failures(Path(temporary))), 7)

    def test_every_unix_socket_passes(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="s") as temporary:
            root = Path(temporary)
            sockets = []
            try:
                for provider in MODULE.PROVIDERS:
                    path = root / "config/evidence/local/cells" / provider / "transit/transit-proxy.sock"
                    path.parent.mkdir(parents=True)
                    instance = socket.socket(socket.AF_UNIX)
                    instance.bind(str(path))
                    sockets.append(instance)
                self.assertEqual(MODULE.failures(root), [])
            finally:
                for instance in sockets:
                    instance.close()


if __name__ == "__main__":
    unittest.main()
