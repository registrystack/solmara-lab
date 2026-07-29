#!/usr/bin/env python3
"""Validate a registryctl test report and require governed request witnesses."""

from __future__ import annotations

import json
import sys
from typing import Any


REPORT_SCHEMA = "registryctl.project_command.v1"
REQUEST_BINDING_REQUIREMENT = "request_to_consultation_binding"
MAX_REPORT_BYTES = 16 * 1024 * 1024


class TestReportError(ValueError):
    """A safe validation error for a registryctl test report."""


def reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TestReportError("the JSON report contains a duplicate field")
        result[key] = value
    return result


def validate_test_report(raw: bytes) -> tuple[str, int, int]:
    if not raw:
        raise TestReportError("registryctl returned an empty report")
    if len(raw) > MAX_REPORT_BYTES:
        raise TestReportError("the JSON report exceeds the size limit")
    try:
        report = json.loads(raw, object_pairs_hook=reject_duplicate_fields)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise TestReportError("registryctl did not return strict UTF-8 JSON") from error
    if not isinstance(report, dict):
        raise TestReportError("the JSON report is not an object")
    if report.get("schema_version") != REPORT_SCHEMA:
        raise TestReportError("the JSON report has an unsupported schema")
    if report.get("status") != "passed":
        raise TestReportError("registryctl did not report a passing fixture suite")
    project = report.get("project")
    if not isinstance(project, str) or not project:
        raise TestReportError("the JSON report has no project identity")

    fixtures = report.get("fixtures")
    if (
        not isinstance(fixtures, list)
        or not fixtures
        or any(
            not isinstance(fixture, dict) or fixture.get("passed") is not True
            for fixture in fixtures
        )
    ):
        raise TestReportError("the JSON report contains a non-passing fixture")

    coverage = report.get("fixture_coverage")
    targets = coverage.get("targets") if isinstance(coverage, dict) else None
    if not isinstance(targets, list) or not targets:
        raise TestReportError("the JSON report has no fixture coverage targets")
    for target in targets:
        requirements = target.get("requirements") if isinstance(target, dict) else None
        if not isinstance(requirements, list):
            raise TestReportError("a fixture coverage target has no requirements")
        bindings = [
            requirement
            for requirement in requirements
            if isinstance(requirement, dict)
            and requirement.get("requirement") == REQUEST_BINDING_REQUIREMENT
        ]
        if len(bindings) != 1 or bindings[0].get("state") != "covered":
            raise TestReportError(
                "every fixture target must cover request-to-consultation binding"
            )
        evidence = bindings[0].get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(item, dict)
                or item.get("kind") != "authored_fixture"
                for item in evidence
            )
        ):
            raise TestReportError(
                "request-to-consultation binding requires authored fixture evidence"
            )
    return project, len(fixtures), len(targets)


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_REPORT_BYTES + 1)
    try:
        project, fixture_count, target_count = validate_test_report(raw)
    except TestReportError as error:
        print(f"registryctl test report invalid: {error}", file=sys.stderr)
        return 1
    print(
        f"PASS: {project}: {fixture_count}/{fixture_count} fixtures passed; "
        f"request witnesses cover {target_count}/{target_count} targets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
