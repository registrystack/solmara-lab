#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
set -a
. "$root/versions.env"
. "$root/.env"
set +a

uv run --project "$root" "$root/scripts/check-signer-public-keys.py"

python3 - <<'PY'
import json
import os
import urllib.request

for name, url in {
    "home": f"http://127.0.0.1:{os.getenv('SOLMARA_HOME_PORT', '4301')}/",
    "portal": f"http://127.0.0.1:{os.getenv('SOLMARA_PORTAL_PORT', '4300')}/",
}.items():
    with urllib.request.urlopen(url, timeout=10) as response:
        if response.status != 200:
            raise SystemExit(f"{name} returned {response.status}")

for authority, port in {"cra": 4311, "nia": 4312, "mosd": 4314, "sipf": 4315, "nagdi": 4316}.items():
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:
        body = json.load(response)
        if body.get("status") != "ok":
            raise SystemExit(f"{authority} Relay is not healthy")
PY
