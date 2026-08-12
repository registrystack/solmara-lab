#!/usr/bin/env python3
"""Project runtime secrets while excluding every provider signing key."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "config/evidence/local/cells"
OUTPUT = ROOT / "runtime/evidence-cells/secrets"
CELL_CLIENTS = {
    "cra": ("cra-pension-evidence", "cra-citizen-evidence"),
    "nia": (), "sro": (),
    "mosd-programme": ("mosd-child-benefit-evidence",),
    "sipf": ("sipf-pension-evidence", "sipf-survivor-evidence"),
    "nagdi": ("nagdi-voucher-evidence", "nagdi-livestock-evidence"),
}


def project(private: Path = PRIVATE, output: Path = OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for cell, clients in CELL_CLIENTS.items():
        destination = output / cell
        destination.mkdir(mode=0o700)
        client_files = tuple(f"{client}-{suffix}" for client in clients for suffix in ("client-id", "client-key"))
        for name in ("audit-hmac-key", "subject-binding-hmac-key", *client_files):
            shutil.copyfile(private / cell / "secrets" / name, destination / name)
            (destination / name).chmod(0o600)
    mint = output / "mint"
    mint.mkdir(mode=0o700)
    shutil.copyfile(private / "mint/secrets/audit-hmac-key", mint / "audit-hmac-key")
    (mint / "audit-hmac-key").chmod(0o600)


if __name__ == "__main__":
    project()
