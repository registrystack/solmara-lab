#!/usr/bin/env python3
"""Print the non-destructive authority-cell rollout operation for one phase."""

from __future__ import annotations

import argparse

PHASES = {
    "side-by-side": "start authority-cell services with public routes disabled",
    "switch": "enable authority-cell public routes after health and evidence checks",
    "disable": "stop superseded services; retain every superseded volume",
}


def operation(phase: str) -> dict[str, str]:
    if phase not in PHASES:
        raise ValueError("unknown rollout phase")
    return {
        "phase": phase,
        "action": PHASES[phase],
        "volumePolicy": "retain",
        "destructiveCommand": "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=tuple(PHASES))
    args = parser.parse_args()
    plan = operation(args.phase)
    for key, value in plan.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
