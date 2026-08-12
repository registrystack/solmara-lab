#!/usr/bin/env python3
"""Prove the Registry Stack v0.18.0 SQLite-extract Evidence starter."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "registry-status"
EXPECTED_SUMMARY = "2 passed, 0 failed (13 cases evaluated)"
Runner = Callable[..., subprocess.CompletedProcess[str]]


class DemoError(RuntimeError):
    """The released SQLite-extract starter did not complete as documented."""


def acquire_tool(name: str, runner: Runner = subprocess.run) -> Path:
    completed = runner(
        [ROOT / "scripts/registry-stack-tool.py", "path", name],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    path = Path(completed.stdout.strip())
    if not path.is_file():
        raise DemoError(f"the pinned {name} downloader returned no executable")
    return path


def run_step(command: list[Path | str], workspace: Path, runner: Runner) -> str:
    completed = runner(
        command,
        cwd=workspace,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(completed.stdout, end="")
    return completed.stdout


def run_demo(workspace: Path, runner: Runner = subprocess.run) -> None:
    if any(workspace.iterdir()):
        raise DemoError(f"demo workspace is not empty: {workspace}")

    evidence = acquire_tool("evidence", runner)
    evidencectl = acquire_tool("evidencectl", runner)
    run_step(
        [
            evidencectl,
            "new",
            PROJECT_NAME,
            "--transport",
            "sqlite-extract",
            "--profile",
            "local",
        ],
        workspace,
        runner,
    )
    output = run_step(
        [
            evidencectl,
            "fixtures",
            "run",
            "--project",
            PROJECT_NAME,
            "--evidence-bin",
            evidence,
            "--explain",
        ],
        workspace,
        runner,
    )
    if EXPECTED_SUMMARY not in output:
        raise DemoError(
            "the v0.18.0 SQLite-extract starter did not report its documented "
            "13-case pass"
        )


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(
            prefix="solmara-evidence-sqlite-extract-"
        ) as directory:
            workspace = Path(directory)
            print(f"Running the v0.18.0 SQLite-extract starter in {workspace}")
            run_demo(workspace)
        print("SQLite-extract Evidence demo passed in a fresh temporary directory")
        return 0
    except (DemoError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stdout:
            print(error.stdout, end="", file=sys.stderr)
        print(f"evidence-sqlite-extract-demo: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
