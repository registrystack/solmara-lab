from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "registryctl_build_output",
    ROOT / "scripts" / "registryctl-build-output.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegistryctlBuildOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        (self.project / "registry-stack.yaml").write_text(
            "version: 1\nregistry:\n  id: example\n",
            encoding="utf-8",
        )
        self.output = self.project / ".registry-stack" / "build" / "local"
        relay = self.output / "private" / "relay" / "config"
        relay.mkdir(parents=True)
        (relay / "relay.yaml").write_text("instance: {}\n", encoding="utf-8")
        notary = self.output / "private" / "notary" / "config"
        notary.mkdir(parents=True)
        (notary / "notary.yaml").write_text("instance: {}\n", encoding="utf-8")

    def report(self, **overrides: object) -> bytes:
        report: dict[str, object] = {
            "schema_version": MODULE.REPORT_SCHEMA,
            "status": "built",
            "project": "example",
            "environment": "local",
            "fixtures": [],
            "semantic_changes": [],
            "baseline": "initial_without_baseline",
            "output": str(self.output),
        }
        report.update(overrides)
        return json.dumps(report).encode("utf-8")

    def test_accepts_the_versioned_project_owned_build_root(self) -> None:
        self.assertEqual(
            MODULE.parse_build_output(
                self.report(),
                project_directory=self.project,
                environment="local",
            ),
            self.output.resolve(),
        )

    def test_rejects_the_wrong_environment_without_echoing_report_values(self) -> None:
        with self.assertRaisesRegex(
            MODULE.BuildReportError,
            "wrong environment binding",
        ) as rejected:
            MODULE.parse_build_output(
                self.report(environment="hosted", secret="must-not-echo"),
                project_directory=self.project,
                environment="local",
            )
        self.assertNotIn("must-not-echo", str(rejected.exception))

    def test_rejects_an_output_root_outside_the_project(self) -> None:
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        with self.assertRaisesRegex(
            MODULE.BuildReportError,
            "not a real project-owned directory",
        ):
            MODULE.parse_build_output(
                self.report(output=str(outside)),
                project_directory=self.project,
                environment="local",
            )

    def test_rejects_an_incomplete_product_closure(self) -> None:
        (self.output / "private" / "notary" / "config" / "notary.yaml").unlink()
        with self.assertRaisesRegex(
            MODULE.BuildReportError,
            "configuration closure is incomplete",
        ):
            MODULE.parse_build_output(
                self.report(),
                project_directory=self.project,
                environment="local",
            )


if __name__ == "__main__":
    unittest.main()
