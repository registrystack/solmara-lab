from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).with_name("smoke-hosted-provisioner-image.py")
SPEC = importlib.util.spec_from_file_location("smoke_hosted_provisioner_image", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HostedProvisionerImageSmokeTests(unittest.TestCase):
    def test_smoke_uses_the_provisioner_owned_bind_hosts(self) -> None:
        provisioner = MODULE._provisioner_module()
        self.assertEqual(provisioner.EXPECTED_BIND_HOST["cra"], "172.29.2.21")
        self.assertEqual(provisioner.EXPECTED_BIND_HOST["mint"], "172.29.1.20")

    def test_container_uses_the_same_bounded_volume_initializer_identity_as_hosted(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            (inputs / "secret").write_text("value", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            with mock.patch.object(MODULE.subprocess, "run") as run:
                MODULE._run(
                    "image@sha256:" + "a" * 64,
                    ["provision"],
                    [
                        (inputs, "/tmp/solmara-provisioning", True),
                        (output, "/provisioned/runtime", False),
                    ],
                )
        self.assertEqual(run.call_count, 2)
        up = run.call_args_list[0]
        self.assertIn("compose", up.args[0])
        self.assertIn("--exit-code-from", up.args[0])
        self.assertNotIn("value", " ".join(up.args[0]))
        self.assertEqual(up.kwargs["env"]["SOLMARA_SMOKE_SECRET_0"], "value")
        down = run.call_args_list[1]
        self.assertIn("down", down.args[0])
        self.assertIn("--volumes", down.args[0])

    def test_success_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, error = StringIO(), StringIO()
            with (
                mock.patch.object(
                    os.sys,
                    "argv",
                    [
                        SCRIPT.name,
                        "--image",
                        "image@sha256:" + "a" * 64,
                        "--state-root",
                        temporary,
                    ],
                ),
                mock.patch.object(MODULE, "smoke") as smoke,
                redirect_stdout(output),
                redirect_stderr(error),
            ):
                self.assertEqual(MODULE.main(), 0)
            smoke.assert_called_once()
            self.assertEqual(
                output.getvalue().strip(), "hosted provisioner image smoke passed"
            )
            self.assertEqual(error.getvalue(), "")

    def test_failure_redacts_dependency_details(self) -> None:
        canary = "PRIVATE-HOSTED-SMOKE-CANARY"
        output, error = StringIO(), StringIO()
        with (
            mock.patch.object(os.sys, "argv", [SCRIPT.name, "--image", "invalid"]),
            mock.patch.object(MODULE, "smoke", side_effect=RuntimeError(canary)),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(MODULE.main(), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue().strip(), MODULE.GENERIC_ERROR)
        self.assertNotIn(canary, error.getvalue())


if __name__ == "__main__":
    unittest.main()
