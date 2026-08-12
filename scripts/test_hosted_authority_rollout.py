from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("hosted-authority-rollout.py")
SPEC = importlib.util.spec_from_file_location("authority_rollout", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HostedAuthorityRolloutTests(unittest.TestCase):
    def test_every_phase_is_recoverable(self) -> None:
        for phase in ("side-by-side", "switch", "disable"):
            plan = MODULE.operation(phase)
            self.assertEqual(plan["volumePolicy"], "retain")
            self.assertEqual(plan["destructiveCommand"], "none")

    def test_unknown_phase_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.operation("delete")


if __name__ == "__main__":
    unittest.main()
