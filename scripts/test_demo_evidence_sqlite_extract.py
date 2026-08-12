from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_demo():
    spec = importlib.util.spec_from_file_location(
        "demo_evidence_sqlite_extract",
        PROJECT_ROOT / "scripts/demo-evidence-sqlite-extract.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load demo-evidence-sqlite-extract.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_evidence_sqlite_extract"] = module
    spec.loader.exec_module(module)
    return module


class EvidenceSqliteExtractDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_demo()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        assets = self.root / "assets"
        assets.mkdir()
        self.evidence = assets / "evidence"
        self.evidencectl = assets / "evidencectl"
        self.evidence.touch()
        self.evidencectl.touch()

    def completed(self, stdout: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")

    def test_demo_downloads_both_pinned_tools_and_proves_all_13_cases(self) -> None:
        calls: list[tuple[list[Path | str], Path | None]] = []

        def runner(command, **kwargs):
            calls.append((command, kwargs.get("cwd")))
            if command[-2:] == ["path", "evidence"]:
                return self.completed(f"{self.evidence}\n")
            if command[-2:] == ["path", "evidencectl"]:
                return self.completed(f"{self.evidencectl}\n")
            if "new" in command:
                return self.completed("Created an editable SQLite-extract project\n")
            return self.completed(
                "PASS: fixtures/record-status.yaml (13 cases)\n"
                "2 passed, 0 failed (13 cases evaluated)\n"
            )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.module.run_demo(self.workspace, runner)

        self.assertEqual(
            calls[0][0],
            [
                self.module.ROOT / "scripts/registry-stack-tool.py",
                "path",
                "evidence",
            ],
        )
        self.assertEqual(calls[1][0][-2:], ["path", "evidencectl"])
        self.assertEqual(
            calls[2][0],
            [
                self.evidencectl,
                "new",
                "registry-status",
                "--transport",
                "sqlite-extract",
                "--profile",
                "local",
            ],
        )
        self.assertEqual(
            calls[3][0],
            [
                self.evidencectl,
                "fixtures",
                "run",
                "--project",
                "registry-status",
                "--evidence-bin",
                self.evidence,
                "--explain",
            ],
        )
        self.assertEqual(calls[2][1], self.workspace)
        self.assertEqual(calls[3][1], self.workspace)
        self.assertIn("13 cases evaluated", stdout.getvalue())

    def test_demo_refuses_to_reuse_a_nonempty_workspace(self) -> None:
        (self.workspace / "existing").touch()
        runner = mock.Mock()

        with self.assertRaisesRegex(self.module.DemoError, "not empty"):
            self.module.run_demo(self.workspace, runner)

        runner.assert_not_called()

    def test_demo_rejects_a_fixture_run_without_the_documented_summary(self) -> None:
        def runner(command, **_kwargs):
            if command[-2:] == ["path", "evidence"]:
                return self.completed(f"{self.evidence}\n")
            if command[-2:] == ["path", "evidencectl"]:
                return self.completed(f"{self.evidencectl}\n")
            if "new" in command:
                return self.completed("created\n")
            return self.completed("1 passed, 1 failed (13 cases evaluated)\n")

        with (
            contextlib.redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(self.module.DemoError, "13-case pass"),
        ):
            self.module.run_demo(self.workspace, runner)


if __name__ == "__main__":
    unittest.main()
