#!/usr/bin/env python3
"""Smoke the Compose portal service and its live BFF wiring."""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "smoke" / "portal-compose.json"


def main() -> int:
    base_url = os.environ.get("SOLMARA_PORTAL_URL", f"http://127.0.0.1:{os.environ.get('SOLMARA_PORTAL_PORT', '4300')}")
    expect_auth_required = truthy(os.environ.get("SOLMARA_PORTAL_EXPECT_AUTH_REQUIRED"))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    root = wait_for_ok(opener, joined_url(base_url, "/"))
    if root.status != 200:
        failures.append(f"portal root did not become ready: {root.status or root.error}")

    login = request_json(opener, "GET", joined_url(base_url, "/auth/login"))
    if login.status != 200:
        failures.append(f"portal login flow returned {login.status or login.error}")

    evaluate = request_json(
        opener,
        "POST",
        joined_url(base_url, "/api/evaluate"),
        {
            "slug": "farmer-voucher",
            "fieldId": "registered-farmer",
        },
    )
    if expect_auth_required:
        if evaluate.status != 401:
            failures.append(f"portal live evaluate should require sign-in, got {evaluate.status or evaluate.error}")
    elif evaluate.status != 200:
        failures.append(f"portal live evaluate returned {evaluate.status or evaluate.error}; body={compact(evaluate.body)}")
    elif not isinstance(evaluate.body, dict) or evaluate.body.get("state") != "verified":
        failures.append(f"portal live evaluate returned unexpected body={compact(evaluate.body)}")

    OUTPUT.write_text(
        json.dumps(
            {
                "base_url": base_url,
                "root_status": root.status,
                "login_status": login.status,
                "evaluate_status": evaluate.status,
                "evaluate_state": (
                    "auth_required"
                    if expect_auth_required and evaluate.status == 401
                    else evaluate.body.get("state") if isinstance(evaluate.body, dict) else None
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if failures:
        for failure in failures:
            print(f"smoke-portal-compose: {failure}", file=sys.stderr)
        print(f"smoke-portal-compose: wrote {display_path(OUTPUT)}", file=sys.stderr)
        return 1

    print(f"smoke-portal-compose: portal live BFF smoke passed; wrote {display_path(OUTPUT)}")
    return 0


class HttpResult:
    def __init__(self, status: int | None, body: Any, error: str = "") -> None:
        self.status = status
        self.body = body
        self.error = error


def wait_for_ok(opener: urllib.request.OpenerDirector, url: str) -> HttpResult:
    deadline = time.monotonic() + float(os.environ.get("SOLMARA_SMOKE_READY_TIMEOUT_SECONDS", "90"))
    last = HttpResult(None, {}, "timeout")
    while time.monotonic() < deadline:
        last = request_json(opener, "GET", url, timeout=2.0)
        if last.status == 200:
            return last
        time.sleep(1)
    return last


def request_json(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    body: Any | None = None,
    timeout: float = 8.0,
) -> HttpResult:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResult(response.status, parse_body(response.read()))
    except urllib.error.HTTPError as error:
        try:
            body = parse_body(error.read())
        finally:
            error.close()
        return HttpResult(error.code, body)
    except Exception as error:
        return HttpResult(None, {}, error.__class__.__name__)


def joined_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")


def compact(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 500 else text[:497] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
