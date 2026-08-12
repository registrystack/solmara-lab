#!/usr/bin/env python3
"""Verify every generated provider public JWK matches its operator private JWK."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("mint", "cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
PUBLIC_MEMBERS = ("alg", "crv", "kid", "kty", "x", "y")


def failures(root: Path = ROOT) -> list[str]:
    result: list[str] = []
    for provider in PROVIDERS:
        private_path = root / "config/evidence/local/cells" / provider / "secrets/signing.jwk"
        public_root = (
            root / "runtime/evidence-cells/mint/public-keys"
            if provider == "mint"
            else root / "runtime/evidence-cells/cells" / provider / "bundle/public-keys"
        )
        try:
            private = json.loads(private_path.read_text(encoding="utf-8"))
            public_path = public_root / f"{private['kid']}.jwk.json"
            public = json.loads(public_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            result.append(f"{provider}: signer material is missing or invalid")
            continue
        if set(public) != set(PUBLIC_MEMBERS) or any(public.get(name) != private.get(name) for name in PUBLIC_MEMBERS):
            result.append(f"{provider}: generated public key does not match operator signer")
    return result


def main() -> int:
    found = failures()
    if found:
        print("\n".join(found), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
