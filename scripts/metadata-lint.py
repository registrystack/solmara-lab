#!/usr/bin/env python3
"""Lint the published Solmara metadata bundle."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "metadata" / "public"


def main() -> int:
    failures: list[str] = []
    api_catalog = load_json(PUBLIC_ROOT / ".well-known" / "api-catalog", failures)
    index = load_json(PUBLIC_ROOT / "metadata" / "index.json", failures)
    catalog = load_json(PUBLIC_ROOT / "metadata" / "catalog.json", failures)
    offerings_payload = load_json(PUBLIC_ROOT / "metadata" / "evidence-offerings.json", failures)
    policies_payload = load_json(PUBLIC_ROOT / "metadata" / "policies.jsonld", failures)
    dcat = load_json(PUBLIC_ROOT / "metadata" / "dcat.jsonld", failures)
    cpsv = load_json(PUBLIC_ROOT / "metadata" / "cpsv-ap.jsonld", failures)

    if failures:
        return report(failures)

    offerings = offerings_payload.get("offerings", [])
    policies = policies_payload.get("@graph", [])
    policy_ids = {policy.get("id") for policy in policies}
    referenced_policies = set()

    for dataset in catalog.get("datasets", []):
        require_text(failures, "dataset", dataset, "title")
        require_text(failures, "dataset", dataset, "description")
        for entity in dataset.get("entities", []):
            label = f"entity {dataset.get('id')}/{entity.get('name')}"
            require_text(failures, label, entity, "title")
            require_text(failures, label, entity, "description")
            if not entity.get("purposes"):
                failures.append(f"{label} has no advertised purpose")
            semantics = entity.get("semantics", {})
            if not semantics.get("concepts"):
                failures.append(f"{label} has no semantics concepts")

    evidence_type_ids = {item.get("id") for item in catalog.get("evidence_types", [])}
    dataset_ids = {item.get("id") for item in catalog.get("datasets", [])}
    service_ids = {item.get("id") for item in catalog.get("public_services", [])}
    for offering in offerings:
        label = f"offering {offering.get('id')}"
        require_text(failures, label, offering, "title")
        require_text(failures, label, offering, "description")
        if offering.get("dataset") not in dataset_ids:
            failures.append(f"{label} references unknown dataset {offering.get('dataset')!r}")
        if offering.get("evidence_type") not in evidence_type_ids:
            failures.append(f"{label} references unknown evidence type {offering.get('evidence_type')!r}")
        if not offering.get("purposes"):
            failures.append(f"{label} has no advertised purpose")
        semantics = offering.get("semantics", {})
        if not semantics.get("concepts"):
            failures.append(f"{label} has no semantics concepts")
        for service in offering.get("public_services", []):
            if service not in service_ids:
                failures.append(f"{label} references unknown public service {service!r}")
        policy = offering.get("policy")
        if policy not in policy_ids:
            failures.append(f"{label} references missing policy {policy!r}")
        else:
            referenced_policies.add(policy)

    for policy in policies:
        if policy.get("id") not in referenced_policies:
            failures.append(f"policy {policy.get('id')} is referenced by no offering")

    for document_name, document in {"api-catalog": api_catalog, "index": index, "dcat": dcat, "cpsv-ap": cpsv}.items():
        if not document:
            failures.append(f"{document_name} is empty")

    api_targets = [
        item.get("href")
        for linkset in api_catalog.get("linkset", [])
        for item in linkset.get("item", [])
    ]
    for href in api_targets:
        if isinstance(href, str) and href.startswith("/"):
            target = PUBLIC_ROOT / href.lstrip("/")
            if not target.exists():
                failures.append(f"api-catalog dangling href {href}")

    artifact_paths = {item.get("path") for item in index.get("artifacts", [])}
    expected_paths = {"metadata/catalog.json", "metadata/evidence-offerings.json", "metadata/dcat.jsonld", "metadata/cpsv-ap.jsonld"}
    for path in expected_paths - artifact_paths:
        failures.append(f"metadata index missing artifact {path}")

    if not dcat.get("dcat:dataset"):
        failures.append("DCAT catalog has no datasets")
    if not cpsv.get("cpsv:PublicService"):
        failures.append("CPSV-AP catalog has no public services")

    return report(failures)


def load_json(path: Path, failures: list[str]) -> dict[str, Any]:
    if not path.exists():
        failures.append(f"missing {path.relative_to(ROOT)}")
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        failures.append(f"{path.relative_to(ROOT)} is invalid JSON: {error}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def require_text(failures: list[str], label: str, item: dict[str, Any], key: str) -> None:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        failures.append(f"{label} missing {key}")


def report(failures: list[str]) -> int:
    if failures:
        for failure in failures:
            print(f"metadata-lint: {failure}", file=sys.stderr)
        return 1
    print("metadata-lint: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
