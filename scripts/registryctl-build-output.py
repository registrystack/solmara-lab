#!/usr/bin/env python3
"""Validate a registryctl build report and print its generated output root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPORT_SCHEMA = "registryctl.project_command.v1"
MAX_REPORT_BYTES = 8 * 1024 * 1024


class BuildReportError(ValueError):
    """A safe validation error for a registryctl build report."""


def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildReportError("the JSON report contains a duplicate field")
        result[key] = value
    return result


def parse_build_output(
    raw: bytes,
    *,
    project_directory: Path,
    environment: str,
) -> Path:
    if not raw:
        raise BuildReportError("registryctl returned an empty report")
    if len(raw) > MAX_REPORT_BYTES:
        raise BuildReportError("the JSON report exceeds the size limit")
    try:
        report = json.loads(raw, object_pairs_hook=reject_duplicate_fields)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise BuildReportError("registryctl did not return strict UTF-8 JSON") from error
    if not isinstance(report, dict):
        raise BuildReportError("the JSON report is not an object")
    if report.get("schema_version") != REPORT_SCHEMA:
        raise BuildReportError("the JSON report has an unsupported schema")
    if report.get("status") != "built":
        raise BuildReportError("registryctl did not report a completed build")
    if report.get("environment") != environment:
        raise BuildReportError("the JSON report has the wrong environment binding")
    if not isinstance(report.get("project"), str) or not report["project"]:
        raise BuildReportError("the JSON report has no project identity")

    output_value = report.get("output")
    if not isinstance(output_value, str) or not output_value:
        raise BuildReportError("the JSON report has no output root")
    output = Path(output_value)

    try:
        project_root = project_directory.resolve(strict=True)
        output_root = (
            output.resolve(strict=True)
            if output.is_absolute()
            else (project_root / output).resolve(strict=True)
        )
        output_root.relative_to(project_root)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        raise BuildReportError(
            "the JSON report output root is not a real project-owned directory"
        ) from error
    if not output_root.is_dir():
        raise BuildReportError("the JSON report output root is not a directory")

    relay_config = output_root / "private" / "relay" / "config"
    notary_config = output_root / "private" / "notary" / "config" / "notary.yaml"
    if not relay_config.is_dir() or not notary_config.is_file():
        raise BuildReportError(
            "the generated Relay or Notary configuration closure is incomplete"
        )
    for required in (relay_config, notary_config):
        try:
            required.resolve(strict=True).relative_to(output_root)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            raise BuildReportError(
                "a generated configuration path escapes the build output root"
            ) from error

    return output_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args(argv)
    raw = sys.stdin.buffer.read(MAX_REPORT_BYTES + 1)
    try:
        output = parse_build_output(
            raw,
            project_directory=args.project_dir,
            environment=args.environment,
        )
    except BuildReportError as error:
        print(f"registryctl build report invalid: {error}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
