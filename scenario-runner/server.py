#!/usr/bin/env python3
"""HTTP API for the Solmara guided scenario engine."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

from scenarios import all_stories, run_scenario_step, scenario_payload


API_VERSION = "solmara-scenario-runner/v1"


class ScenarioRunnerHandler(BaseHTTPRequestHandler):
    server_version = "SolmaraScenarioRunner/1.0"

    def do_GET(self) -> None:
        parts = path_parts(self.path)
        if parts == ["health"]:
            self.write_json({"status": "ok", "service": "scenario-runner"})
            return
        if parts == ["v1", "scenarios"]:
            self.write_json(scenario_payload(config(), lab_mode=lab_mode()))
            return
        if len(parts) == 3 and parts[:2] == ["v1", "scenarios"]:
            payload = scenario_payload(config(), parts[2], lab_mode=lab_mode())
            status = HTTPStatus.NOT_FOUND if "error" in payload else HTTPStatus.OK
            self.write_json(payload, status)
            return
        if parts == ["v1", "stories"]:
            self.write_json({"schema_version": API_VERSION, "stories": all_stories()})
            return
        self.write_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parts = path_parts(self.path)
        if len(parts) == 6 and parts[:2] == ["v1", "scenarios"] and parts[3] == "steps" and parts[5] == "run":
            body = self.read_body()
            scenario_id = parts[2]
            step_id = parts[4]
            result = run_scenario_step(config(body), scenario_id, step_id, lab_mode=lab_mode(body))
            status = HTTPStatus.NOT_FOUND if result.get("friendly", {}).get("title") == "Unknown scenario." else HTTPStatus.OK
            self.write_json({"schema_version": API_VERSION, "scenario_id": scenario_id, "result": result}, status)
            return
        self.write_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("SCENARIO_RUNNER_ACCESS_LOG", "").lower() in {"1", "true", "yes"}:
            super().log_message(format, *args)


def config(body: dict[str, Any] | None = None) -> dict[str, Any]:
    return body.get("config", {}) if body else {}


def lab_mode(body: dict[str, Any] | None = None) -> str:
    if body and isinstance(body.get("lab_mode"), str):
        return str(body["lab_mode"])
    return os.environ.get("SOLMARA_LAB_MODE", "local")


def path_parts(path: str) -> list[str]:
    parsed = urlparse(path)
    return [unquote(part) for part in parsed.path.split("/") if part]


def main() -> int:
    host = os.environ.get("SCENARIO_RUNNER_HOST", "127.0.0.1")
    port = int(os.environ.get("SCENARIO_RUNNER_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), ScenarioRunnerHandler)
    print(f"scenario-runner listening on http://{host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
