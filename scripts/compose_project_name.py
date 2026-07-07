#!/usr/bin/env python3
"""Print the default Docker Compose project name for this checkout."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compose_project_name(root: Path = ROOT) -> str:
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:10]
    return f"solmara-lab-{digest}"


def main() -> int:
    print(compose_project_name(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
