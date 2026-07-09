#!/usr/bin/env python3
"""Restrict legacy NID aliases to explicit migration fields."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".svelte-kit",
    "__pycache__",
    "build",
    "node_modules",
    "output",
    "test-results",
    "vendor",
}
EXCLUDED_FILES = {"AGENTS.md", "check-fiction.sh", "check-nid-aliases.py"}


def csv_has_legacy_nid(path: Path) -> bool:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return "legacy_nid" in next(csv.reader(handle), [])
    except (OSError, UnicodeDecodeError):
        return False


def allowed(path: Path, line: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if "legacy_nid" in line:
        return True
    if rel == "generator/solmara_lab/generate.py" and "Persona(" in line:
        return True
    return path.suffix == ".csv" and csv_has_legacy_nid(path)


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.is_file() and path.name not in EXCLUDED_FILES:
            files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(lines, start=1):
            if "NID-" in line and not allowed(path, line):
                failures.append(f"{path.relative_to(ROOT)}:{line_no}:{line}")

    if failures:
        print("NID aliases are allowed only as legacy_nid migration fields.", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
