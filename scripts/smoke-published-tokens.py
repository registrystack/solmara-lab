#!/usr/bin/env python3
"""Off-script skeptic smoke (spec DoD 9).

Use the published demo tokens exactly as the engineer door hands them out and
confirm the two off-script attempts a skeptic would make get clean refusals with
stable problem codes:

1. A wrong-purpose evaluation returns 403 with `pdp.purpose_not_permitted`.
2. A raw-row read attempt (disclosure="raw") is refused with a stable code and
   never returns a 2xx that could leak a source row.

Message text is never asserted; only stable codes and status ranges.
"""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scenarios.common import (  # noqa: E402
    FEDERATED_BUNDLE_FORMAT,
    PURPOSES,
    auth_headers,
    evaluation_body,
    http_json,
    joined_url,
)

# The published demo tokens the engineer door exposes: name -> (url env, token env).
CHILD_URL_ENV = "CHILD_BENEFIT_FEDERATOR_URL"
CHILD_URL_DEFAULT = "http://127.0.0.1:4321"
CHILD_TOKEN_ENV = "CHILD_BENEFIT_FEDERATOR_TOKEN"

POSITIVE_SUBJECT = "2300010248"
CLAIM_IDS = ["birth-is-registered"]


def problem_code(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    code = body.get("code")
    if isinstance(code, str) and code:
        return code
    type_uri = body.get("type")
    if isinstance(type_uri, str) and "/" in type_uri:
        return type_uri.rstrip("/").rsplit("/", 1)[-1]
    return ""


def main() -> int:
    load_dotenv(ROOT / ".env")
    token = os.environ.get(CHILD_TOKEN_ENV)
    if not token:
        print(f"smoke-published-tokens: missing {CHILD_TOKEN_ENV}; run `just generate` before live smoke", file=sys.stderr)
        return 1

    base_url = os.environ.get(CHILD_URL_ENV, CHILD_URL_DEFAULT)
    eval_url = joined_url(base_url, "/v1/evaluations")
    failures: list[str] = []

    # 1. Wrong purpose: ask the child benefit notary under a pension purpose.
    wrong_headers = auth_headers(token, PURPOSES["pension_payment"], FEDERATED_BUNDLE_FORMAT)
    wrong_body = evaluation_body(POSITIVE_SUBJECT, CLAIM_IDS, scheme="solmara_uin", format=FEDERATED_BUNDLE_FORMAT)
    wrong = http_json("POST", eval_url, wrong_headers, wrong_body, timeout=8.0)
    wrong_code = problem_code(wrong.body)
    if wrong.status != 403:
        failures.append(f"wrong-purpose: expected HTTP 403, got {wrong.status}")
    if wrong_code != "pdp.purpose_not_permitted":
        failures.append(f"wrong-purpose: expected code pdp.purpose_not_permitted, got '{wrong_code}'")

    # 2. Raw-row read attempt: ask for the raw source row under a permitted purpose.
    raw_headers = auth_headers(token, PURPOSES["child_benefit"], FEDERATED_BUNDLE_FORMAT)
    raw_body = evaluation_body(
        POSITIVE_SUBJECT, CLAIM_IDS, scheme="solmara_uin", disclosure="raw", format=FEDERATED_BUNDLE_FORMAT
    )
    raw = http_json("POST", eval_url, raw_headers, raw_body, timeout=8.0)
    raw_code = problem_code(raw.body)
    if not (isinstance(raw.status, int) and 400 <= raw.status < 500):
        failures.append(f"raw-row attempt: expected a 4xx refusal, got {raw.status}")
    if not raw_code:
        failures.append("raw-row attempt: expected a stable problem code, got none")

    if failures:
        for failure in failures:
            print(f"smoke-published-tokens: {failure}", file=sys.stderr)
        return 1

    print(
        "smoke-published-tokens: published-token wrong-purpose (403 "
        f"{wrong_code}) and raw-row attempt ({raw.status} {raw_code}) both refused cleanly"
    )
    return 0


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        if raw_value == "":
            os.environ[key] = ""
            continue
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


if __name__ == "__main__":
    raise SystemExit(main())
