#!/usr/bin/env python3
"""Render every guided story request without sending network calls."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    "scenarios.child_benefit",
    "scenarios.pension_survivor",
    "scenarios.farmer_voucher",
    "scenarios.citizen",
]


def validate_request(module_name: str, step_id: str, request: dict[str, Any]) -> None:
    method = request.get("method")
    url = request.get("url")
    headers = request.get("headers")
    if method == "MULTI":
        if url != "solmara://registry-evidence":
            raise ValueError(
                f"{module_name}:{step_id}: expected Evidence collection URL, got {url!r}"
            )
        if not isinstance(request.get("purpose"), str):
            raise ValueError(f"{module_name}:{step_id}: missing Evidence purpose")
        requests = request.get("requests")
        if not isinstance(requests, list) or not requests:
            raise ValueError(
                f"{module_name}:{step_id}: Evidence collection has no requests"
            )
        for index, authority_request in enumerate(requests):
            if not isinstance(authority_request, dict):
                raise ValueError(
                    f"{module_name}:{step_id}: Evidence request {index} is invalid"
                )
            validate_request(
                module_name,
                f"{step_id}/authority-{index + 1}",
                authority_request,
            )
        return
    if method not in {"GET", "POST"}:
        raise ValueError(f"{module_name}:{step_id}: invalid method {method!r}")
    if not isinstance(url, str) or not (
        url.startswith("http://127.0.0.1:")
        or url.startswith("https://localhost:")
        or url.startswith("https://evidence.solmara.invalid/")
    ):
        raise ValueError(f"{module_name}:{step_id}: expected local Evidence URL, got {url!r}")
    if not isinstance(headers, dict):
        raise ValueError(f"{module_name}:{step_id}: missing headers")
    if "Data-Purpose" not in headers and "Authorization" not in headers:
        raise ValueError(f"{module_name}:{step_id}: missing application or Evidence authorization")
    for header in ("Authorization", "x-api-key"):
        if header in headers and "runtime token hidden" not in headers[header] and "runtime token missing" not in headers[header]:
            raise ValueError(f"{module_name}:{step_id}: {header} header was not redacted")
    if method == "POST" and "body" not in request:
        raise ValueError(f"{module_name}:{step_id}: POST preview is missing a body")


def main() -> int:
    output: dict[str, Any] = {}
    for module_name in SCENARIOS:
        module = importlib.import_module(module_name)
        story = module.story()
        previews = []
        for step in story["steps"]:
            step_id = step["id"]
            request = module.preview_step({}, step_id)
            validate_request(module_name, step_id, request)
            previews.append({"step_id": step_id, "request": request})
        output[story["id"]] = previews

    out_path = ROOT / "output" / "smoke" / "story-previews.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
