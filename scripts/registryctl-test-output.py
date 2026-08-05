#!/usr/bin/env python3
"""Validate a current-main registryctl fixture and coverage report."""

from __future__ import annotations

import json
import sys
from typing import Any


REPORT_SCHEMA = "registryctl.project_command.v1"
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
        if not isinstance(target, dict):
            raise TestReportError("a fixture coverage target is not an object")
        identity = target.get("identity")
        compiled = target.get("compiled_contract")
        inventory = target.get("fixture_inventory")
        if (
            target.get("fixture_set_state") != "fixture_bearing"
            or not isinstance(identity, dict)
            or not isinstance(identity.get("integration"), str)
            or not isinstance(identity.get("capability"), str)
            or not isinstance(compiled, dict)
            or compiled.get("kind") != "compiled_contract"
            or not isinstance(compiled.get("digest"), str)
            or not compiled["digest"].startswith("sha256:")
            or not isinstance(inventory, list)
            or not inventory
            or any(
                not isinstance(item, dict)
                or item.get("pass_state") != "passed"
                or not isinstance(item.get("fixture_digest"), str)
                or not item["fixture_digest"].startswith("sha256:")
                for item in inventory
            )
        ):
            raise TestReportError("every coverage target must bind passing fixtures to a compiled contract")
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
        f"compiled fixture coverage includes {target_count}/{target_count} targets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
