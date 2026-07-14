#!/usr/bin/env python3
"""Fail if committed config appears to contain raw credentials."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [
    "ministries",
    "metadata",
    "projects",
    "runtime/registry-projects",
    "compose.yaml",
    "compose.esignet.yaml",
]
RAW_SECRET_KEYS = re.compile(
    r"(?i)\b(token|secret|password|private[_-]?key|client[_-]?secret)\s*:\s*['\"]?[^${\s][^#\n]+"
)
ALLOWED = (
    "token_env:",
    "private_jwk_env:",
    "hash_secret_env:",
    "POSTGRES_PASSWORD:",
    "REGISTRY_NOTARY_REPLAY_REDIS_URL:",
)
WORKLOAD_TOKEN_VOLUME = re.compile(
    r"^\s*-\s*[a-z0-9-]+-workload-token:/run/secrets(?::ro)?\s*$"
)
PROJECT_SECRET_REFERENCE = re.compile(
    r"^\s*[a-z][a-z0-9_]*:\s*\{\s*secret:\s*[A-Z][A-Z0-9_]*\s*\}\s*$"
)


def line_is_allowed(line: str) -> bool:
    return (
        any(marker in line for marker in ALLOWED)
        or bool(WORKLOAD_TOKEN_VOLUME.fullmatch(line))
        or bool(PROJECT_SECRET_REFERENCE.fullmatch(line))
    )


def iter_files() -> list[Path]:
    files: list[Path] = []
    for entry in SCAN_DIRS:
        path = ROOT / entry
        if path.is_file():
            files.append(path)
        elif path.exists():
            files.extend(p for p in path.rglob("*") if p.is_file())
    files.extend(sorted(ROOT.glob("compose.coolify*.yaml")))
    return files


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        if (
            path.suffix not in {".yaml", ".yml", ".env", ""}
            and path.name
            not in {
                "compose.yaml",
                "compose.esignet.yaml",
            }
            and not path.name.startswith("compose.coolify")
        ):
            continue
        for line_no, line in enumerate(
            path.read_text(errors="ignore").splitlines(), start=1
        ):
            if line_is_allowed(line):
                continue
            if RAW_SECRET_KEYS.search(line):
                failures.append(
                    f"{path.relative_to(ROOT)}:{line_no}: possible raw secret"
                )

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
