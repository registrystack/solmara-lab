#!/usr/bin/env python3
"""Publish the Solmara metadata bundle served by static-metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSEMBLY = ROOT / "metadata" / "assembly.yaml"
CHILD_BENEFIT_PURPOSE = (
    "https://id.registrystack.org/solmara/purpose/child-benefit-review"
)
PENSION_PAYMENT_PURPOSE = (
    "https://id.registrystack.org/solmara/purpose/pension-payment-review"
)
SURVIVOR_BENEFIT_PURPOSE = (
    "https://id.registrystack.org/solmara/purpose/survivor-benefit-determination"
)
VOUCHER_REVIEW_PURPOSE = (
    "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"
)
CHILD_BENEFIT_COLLECTION_MEDIA_TYPE = "application/json"
CHILD_BENEFIT_FEDERATOR_URL = (
    "https://child-benefit-federator.solmara.registrystack.org"
)

DATASET_OFFERING_DEFAULTS = {
    "cra-civil": {
        "evidence_type": "birth-registration-evidence",
        "entity": "civil_person",
        "service": "child-benefit-review",
        "endpoint": "https://cra-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://cra-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "concepts": [
            "https://publicschema.org/crvs/Birth",
            "https://publicschema.org/crvs/Death",
        ],
    },
    "nia-population": {
        "evidence_type": "population-status-evidence",
        "entity": "person",
        "service": "child-benefit-review",
        "endpoint": "https://nia-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://nia-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "concepts": ["https://publicschema.org/Person"],
    },
    "sro-social": {
        "evidence_type": "household-poverty-evidence",
        "entity": "household",
        "service": "child-benefit-review",
        "endpoint": "https://sro-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://sro-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "concepts": [
            "https://publicschema.org/Household",
            "https://publicschema.org/SocioEconomicProfile",
        ],
    },
    "mosd-programme": {
        "evidence_type": "beneficiary-enrollment-evidence",
        "entity": "enrollment",
        "service": "child-benefit-review",
        "endpoint": "https://programme-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://programme-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "concepts": ["https://publicschema.org/sp/Enrollment"],
    },
    "sipf-pensions": {
        "evidence_type": "pension-case-evidence",
        "entity": "pension_case",
        "service": "pension-survivor-review",
        "endpoint": "https://sipf-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://sipf-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [PENSION_PAYMENT_PURPOSE, SURVIVOR_BENEFIT_PURPOSE],
        "concepts": ["https://id.registrystack.org/solmara/semantics/pension-case"],
    },
    "nagdi-agriculture": {
        "evidence_type": "farmer-voucher-evidence",
        "entity": "farmer_voucher",
        "service": "nagdi-voucher-review",
        "endpoint": "https://nagdi-notary.solmara.registrystack.org/v1/evaluations",
        "discovery": "https://nagdi-notary.solmara.registrystack.org/.well-known/evidence-service",
        "purposes": [VOUCHER_REVIEW_PURPOSE],
        "concepts": ["https://publicschema.org/Farm"],
    },
}

GRAY_REGISTRIES = [
    {
        "id": "land-cadastre",
        "title": "Land registry and cadastre",
        "owner": "Ministry of Lands and Survey",
        "wave": 2,
    },
    {
        "id": "taxpayer",
        "title": "Taxpayer registry",
        "owner": "Solmara Revenue Authority",
        "wave": 2,
    },
    {
        "id": "business",
        "title": "Business registry",
        "owner": "Solmara Business Registration Service",
        "wave": 2,
    },
    {
        "id": "beneficial-ownership",
        "title": "Beneficial ownership register",
        "owner": "Solmara Business Registration Service",
        "wave": 2,
    },
    {
        "id": "disability",
        "title": "Disability registry",
        "owner": "Disability Assessment Board",
        "wave": 3,
    },
    {
        "id": "education",
        "title": "Education learner registry",
        "owner": "Ministry of Education",
        "wave": 3,
    },
    {
        "id": "health-facilities",
        "title": "Health facility registry",
        "owner": "Ministry of Health",
        "wave": 3,
    },
    {
        "id": "patient-immunization",
        "title": "Patient and immunization registry",
        "owner": "Ministry of Health",
        "wave": None,
    },
    {
        "id": "transport-licences",
        "title": "Vehicle and driving licence registry",
        "owner": "Ministry of Transport",
        "wave": None,
    },
    {
        "id": "customs-traders",
        "title": "Customs trader registry",
        "owner": "Customs Service",
        "wave": None,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assembly", nargs="?", type=Path, default=DEFAULT_ASSEMBLY)
    parser.add_argument(
        "--check", action="store_true", help="Fail if committed output is stale"
    )
    args = parser.parse_args()

    assembly_path = abs_path(args.assembly)
    assembly = load_yaml(assembly_path)
    manifest_path = abs_path(assembly["publisher"]["manifest"])
    site_root = abs_path(assembly["publisher"].get("site_root", "metadata/public"))
    out_root = abs_path(assembly["publisher"].get("output", "metadata/public/metadata"))

    manifest = load_yaml(manifest_path)
    fragment_index = load_fragments(assembly)
    bundle = build_bundle(manifest, fragment_index)
    generated = render_files(manifest_path, manifest, bundle)

    if args.check:
        stale = stale_files(site_root, generated)
        if stale:
            for path in stale:
                print(f"metadata publish output is stale: {path}")
            return 1
        return 0

    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    (site_root / ".well-known").mkdir(parents=True, exist_ok=True)

    for relative, payload in generated.items():
        target = site_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            target.write_bytes(payload)
        else:
            target.write_text(payload, encoding="utf-8")

    print(f"published metadata artifacts to {out_root.relative_to(ROOT)}")
    return 0


def abs_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_fragments(assembly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_dataset: dict[str, dict[str, Any]] = {}
    for fragment_path in assembly.get("source_fragments", []):
        fragment = load_yaml(abs_path(fragment_path))
        authority = fragment.get("authority", {})
        purposes = fragment.get("purposes", [])
        for dataset in fragment.get("datasets", []):
            by_dataset[dataset["id"]] = {
                "authority": authority,
                "purposes": purposes,
                "application_profiles": fragment.get("application_profiles", []),
            }
    return by_dataset


def build_bundle(
    manifest: dict[str, Any], fragment_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    authorities = {
        authority["id"]: authority for authority in manifest.get("authorities", [])
    }
    evidence_types = {item["id"]: item for item in manifest.get("evidence_types", [])}
    services = {item["id"]: item for item in manifest.get("public_services", [])}
    data_services = {item["id"]: item for item in manifest.get("data_services", [])}
    datasets = [
        normalize_dataset(dataset, fragment_index)
        for dataset in manifest.get("datasets", [])
    ]
    offerings = []
    for dataset in datasets:
        source_offerings = dataset.pop("source_evidence_offerings", [])
        if source_offerings:
            offerings.extend(
                normalize_source_offering(dataset, offering, authorities)
                for offering in source_offerings
            )
        else:
            offerings.append(synthetic_offering(dataset, authorities))

    # NAgDI has two live evidence paths in wave 1; keep both visible to the visitor center.
    if not any(
        offering["id"] == "nagdi-agriculture-livestock-movement-offering"
        for offering in offerings
    ):
        nagdi = next(
            dataset for dataset in datasets if dataset["id"] == "nagdi-agriculture"
        )
        livestock = synthetic_offering(
            nagdi,
            authorities,
            evidence_type="livestock-movement-evidence",
            entity="livestock_movement",
        )
        livestock["id"] = "nagdi-agriculture-livestock-movement-offering"
        livestock["title"] = "NAgDI livestock movement evidence offering"
        livestock["description"] = (
            "Livestock movement-control predicates for permit checks."
        )
        livestock["public_services"] = ["livestock-movement-control"]
        livestock["purposes"] = [
            "https://id.registrystack.org/solmara/purpose/livestock-movement-control"
        ]
        livestock["semantics"]["concepts"] = ["https://publicschema.org/livestock-type"]
        offerings.append(livestock)

    collection_offering_id = "solmara.child-benefit.authority-predicate-collection"
    if not any(offering["id"] == collection_offering_id for offering in offerings):
        offerings.append(child_benefit_collection_offering(authorities))

    policies = [policy_for_offering(offering) for offering in offerings]
    catalog = {
        "schema_version": "registry-manifest-catalog/v1",
        "id": manifest["catalog"]["id"],
        "title": text(manifest["catalog"].get("title"), manifest["catalog"]["id"]),
        "description": text(manifest["catalog"].get("description"), ""),
        "publisher": manifest["catalog"].get("publisher", {}),
        "application_profiles": manifest["catalog"].get("application_profiles", []),
        "authorities": list(authorities.values()),
        "datasets": datasets,
        "gray_registries": GRAY_REGISTRIES,
        "evidence_types": list(evidence_types.values()),
        "public_services": list(services.values()),
        "data_services": list(data_services.values()),
    }
    return {
        "catalog": catalog,
        "evidence_offerings": offerings,
        "policies": policies,
        "dcat": dcat_catalog(catalog),
        "cpsv_ap": cpsv_catalog(catalog, offerings),
        "ogc_records": ogc_records(catalog),
    }


def normalize_dataset(
    dataset: dict[str, Any], fragment_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    fragment = fragment_index.get(dataset["id"], {})
    defaults = DATASET_OFFERING_DEFAULTS.get(dataset["id"], {})
    entities = [
        normalize_entity(item, fragment.get("purposes", []), defaults)
        for item in dataset.get("entities", [])
    ]
    return {
        "id": dataset["id"],
        "title": text(dataset.get("title"), humanize(dataset["id"])),
        "description": text(
            dataset.get("description"), f"{humanize(dataset['id'])} published metadata."
        ),
        "access_rights": dataset.get("access_rights", "restricted"),
        "authority": fragment.get("authority", {}),
        "application_profiles": fragment.get("application_profiles", []),
        "purposes": fragment.get("purposes", []),
        "entities": entities,
        "source_evidence_offerings": dataset.get("evidence_offerings", []),
    }


def normalize_entity(
    entity: str | dict[str, Any], purposes: list[str], defaults: dict[str, Any]
) -> dict[str, Any]:
    if isinstance(entity, str):
        entity = {"name": entity}
    fields = entity.get("fields", [])
    concepts = sorted(
        {concept for field in fields for concept in field.get("concepts", [])}
    )
    if not concepts:
        concepts = defaults.get(
            "concepts",
            ["https://id.registrystack.org/solmara/semantics/registry-record"],
        )
    return {
        "name": entity["name"],
        "title": text(entity.get("title"), humanize(entity["name"])),
        "description": text(
            entity.get("description"), f"{humanize(entity['name'])} entity metadata."
        ),
        "identifiers": entity.get("identifiers", []),
        "fields": fields,
        "purposes": purposes,
        "semantics": {"concepts": concepts, "application_profiles": ["cpsv-ap"]},
    }


def normalize_source_offering(
    dataset: dict[str, Any], offering: dict[str, Any], authorities: dict[str, Any]
) -> dict[str, Any]:
    default = synthetic_offering(
        dataset,
        authorities,
        evidence_type=offering.get("evidence_type"),
        entity=offering.get("entity"),
    )
    policy = offering.get("policy") if isinstance(offering.get("policy"), dict) else {}
    default.update(
        {
            "id": offering["id"],
            "iri": offering.get("iri", default["iri"]),
            "title": text(offering.get("title"), default["title"]),
            "description": text(offering.get("description"), default["description"]),
            "lookup_keys": offering.get("lookup_keys", []),
            "public_services": offering.get(
                "procedure_contexts", default["public_services"]
            ),
            "access": offering.get("access", default["access"]),
            "purposes": policy.get("purpose", dataset["purposes"]),
        }
    )
    default["policy"] = f"{default['id']}-policy"
    return default


def synthetic_offering(
    dataset: dict[str, Any],
    authorities: dict[str, Any],
    *,
    evidence_type: str | None = None,
    entity: str | None = None,
) -> dict[str, Any]:
    defaults = DATASET_OFFERING_DEFAULTS.get(dataset["id"], {})
    evidence_type = evidence_type or defaults.get(
        "evidence_type", f"{dataset['id']}-evidence"
    )
    entity = entity or defaults.get("entity") or dataset["entities"][0]["name"]
    authority = dataset.get("authority", {})
    authority_id = authority.get("id", dataset["id"])
    endpoint = defaults.get(
        "endpoint", "https://metadata.solmara.registrystack.org/v1/evaluations"
    )
    discovery = defaults.get(
        "discovery",
        "https://metadata.solmara.registrystack.org/.well-known/evidence-service",
    )
    offering_id = f"{dataset['id']}-{evidence_type.replace('-evidence', '')}-offering"
    purposes = defaults.get("purposes", dataset.get("purposes", []))
    return {
        "id": offering_id,
        "iri": f"https://id.registrystack.org/solmara/evidence-offerings/{slug(offering_id)}",
        "title": f"{dataset['title']} evidence offering",
        "description": f"Purpose-limited evidence predicates from {dataset['title']}.",
        "dataset": dataset["id"],
        "entity": entity,
        "evidence_type": evidence_type,
        "issuing_authority": authorities.get(authority_id, authority),
        "lookup_keys": ["uin"]
        if entity not in {"farmer_voucher", "livestock_movement"}
        else ["farmer_id"],
        "public_services": [defaults.get("service", "citizen-self-service")],
        "access": {
            "kind": "evidence-verification-api",
            "conforms_to": "https://spec.openapis.org/oas/v3.1.0",
            "endpoint_url": endpoint,
            "discovery_url": discovery,
        },
        "purposes": purposes,
        "semantics": {
            "concepts": defaults.get(
                "concepts",
                ["https://id.registrystack.org/solmara/semantics/registry-record"],
            ),
            "application_profiles": ["cpsv-ap"],
        },
        "policy": f"{offering_id}-policy",
    }


def child_benefit_collection_offering(authorities: dict[str, Any]) -> dict[str, Any]:
    offering_id = "solmara.child-benefit.authority-predicate-collection"
    return {
        "id": offering_id,
        "iri": "https://id.registrystack.org/solmara/evidence-offerings/child-benefit-authority-predicate-collection",
        "title": "Child Benefit Authority Predicate Collection",
        "description": (
            "A transient collection of source-owned child benefit predicates. "
            "It contains no copied source rows and no composed eligibility decision."
        ),
        "dataset": "mosd-programme",
        "entity": "enrollment",
        "evidence_type": "child-benefit-authority-predicate-collection-evidence",
        "issuing_authority": authorities["mosd-programme-mis"],
        "lookup_keys": ["uin"],
        "public_services": ["child-benefit-review"],
        "access": {
            "kind": "authority-predicate-collection-api",
            "conforms_to": "https://id.registrystack.org/solmara/contracts/authority-predicate-collection/v1",
            "endpoint_url": f"{CHILD_BENEFIT_FEDERATOR_URL}/v1/evaluations",
            "discovery_url": f"{CHILD_BENEFIT_FEDERATOR_URL}/v1/claims",
            "media_type": CHILD_BENEFIT_COLLECTION_MEDIA_TYPE,
            "ruleset": "source-owned-child-benefit-predicates-v1",
        },
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "semantics": {
            "concepts": [
                "https://publicschema.org/Person",
                "https://publicschema.org/crvs/Birth",
                "https://publicschema.org/Household",
                "https://publicschema.org/sp/Enrollment",
            ],
            "application_profiles": ["cpsv-ap"],
        },
        "policy": "solmara-child-benefit-authority-predicate-collection-policy",
    }


def policy_for_offering(offering: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": {"odrl": "http://www.w3.org/ns/odrl/2/"},
        "uid": f"https://id.registrystack.org/solmara/policies/{offering['policy']}",
        "id": offering["policy"],
        "type": "odrl:Set",
        "target": offering["iri"],
        "profile": "https://www.w3.org/TR/odrl-model/",
        "permission": [
            {
                "action": "use",
                "constraint": [
                    {
                        "leftOperand": "purpose",
                        "operator": "isAnyOf",
                        "rightOperand": offering["purposes"],
                    }
                ],
            }
        ],
    }


def dcat_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": {
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@type": "dcat:Catalog",
        "@id": "https://metadata.solmara.registrystack.org/metadata/dcat.jsonld",
        "dct:title": catalog["title"],
        "dct:description": catalog["description"],
        "dcat:dataset": [
            {
                "@id": f"https://id.registrystack.org/solmara/datasets/{dataset['id']}",
                "dct:title": dataset["title"],
            }
            for dataset in catalog["datasets"]
        ],
    }


def cpsv_catalog(
    catalog: dict[str, Any], offerings: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "@context": {
            "cpsv": "http://purl.org/vocab/cpsv#",
            "dct": "http://purl.org/dc/terms/",
        },
        "@type": "cpsv:PublicServiceCatalog",
        "@id": "https://metadata.solmara.registrystack.org/metadata/cpsv-ap.jsonld",
        "dct:title": "Solmara Wave 1 public services",
        "cpsv:PublicService": catalog["public_services"],
        "solmara:evidenceOfferings": offerings,
    }


def ogc_records(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": dataset["id"],
                "geometry": None,
                "properties": {
                    "title": dataset["title"],
                    "authority": dataset["authority"].get("name", ""),
                },
            }
            for dataset in catalog["datasets"]
        ],
    }


def render_files(
    manifest_path: Path, manifest: dict[str, Any], bundle: dict[str, Any]
) -> dict[Path, str | bytes]:
    files: dict[Path, str | bytes] = {
        Path("metadata/metadata.yaml"): manifest_path.read_text(encoding="utf-8"),
        Path("metadata/catalog.json"): json_text(bundle["catalog"]),
        Path("metadata/evidence-offerings.json"): json_text(
            {
                "schema_version": "registry-manifest-evidence-offerings/v1",
                "offerings": bundle["evidence_offerings"],
            }
        ),
        Path("metadata/policies.jsonld"): json_text({"@graph": bundle["policies"]}),
        Path("metadata/dcat.jsonld"): json_text(bundle["dcat"]),
        Path("metadata/cpsv-ap.jsonld"): json_text(bundle["cpsv_ap"]),
        Path("metadata/cpsv-ap"): json_text(bundle["cpsv_ap"]),
        Path("metadata/shacl.jsonld"): json_text({"@graph": []}),
        Path("metadata/ogc-records/items.json"): json_text(bundle["ogc_records"]),
    }
    for offering in bundle["evidence_offerings"]:
        files[Path("metadata/evidence-offerings") / f"{offering['id']}.json"] = (
            json_text(offering)
        )
    for policy in bundle["policies"]:
        files[Path("metadata/policies") / f"{policy['id']}.jsonld"] = json_text(policy)

    index = metadata_index(files, bundle["catalog"])
    files[Path("metadata/index.json")] = json_text(index)
    files[Path(".well-known/api-catalog")] = json_text(api_catalog())
    files[Path(".well-known/registry-manifest.json")] = json_text(
        {
            "schema_version": "registry-manifest-discovery/v1",
            "index": "/metadata/index.json",
            "catalog": "/metadata/catalog.json",
        }
    )
    return files


def metadata_index(
    files: dict[Path, str | bytes], catalog: dict[str, Any]
) -> dict[str, Any]:
    artifacts = []
    for relative, payload in files.items():
        if str(relative).startswith(".well-known/"):
            continue
        raw = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        artifacts.append(
            {
                "path": str(relative),
                "media_type": media_type(relative),
                "sha256": sha256_uri(raw),
            }
        )
    artifacts.sort(key=lambda item: item["path"])
    return {
        "schema_version": "registry-manifest-index/v1",
        "catalog_id": catalog["id"],
        "artifacts": artifacts,
        "manifest": "/metadata/metadata.yaml",
        "catalog": "/metadata/catalog.json",
        "evidence_offerings": "/metadata/evidence-offerings.json",
        "policies": "/metadata/policies.jsonld",
        "dcat": "/metadata/dcat.jsonld",
        "service_catalogues": [
            {"id": "cpsv-ap", "version": "3.2.0", "url": "/metadata/cpsv-ap.jsonld"}
        ],
        "shacl": "/metadata/shacl.jsonld",
        "ogc_records_items": "/metadata/ogc-records/items.json",
        "application_profiles": catalog["application_profiles"],
    }


def api_catalog() -> dict[str, Any]:
    items = [
        {
            "href": "/metadata/catalog.json",
            "type": "application/json",
            "title": "Registry metadata catalog",
        },
        {
            "href": "/metadata/dcat.jsonld",
            "type": "application/ld+json",
            "title": "Base DCAT catalog",
        },
        {
            "href": "/metadata/cpsv-ap.jsonld",
            "type": "application/ld+json",
            "title": "cpsv-ap service catalogue",
        },
        {
            "href": "/metadata/evidence-offerings.json",
            "type": "application/json",
            "title": "Evidence offerings",
        },
        {
            "href": "/metadata/policies.jsonld",
            "type": "application/ld+json",
            "title": "Policy metadata",
        },
        {
            "href": "/metadata/ogc-records/items.json",
            "type": "application/geo+json",
            "title": "OGC Records item collection",
        },
    ]
    return {
        "linkset": [
            {
                "anchor": "/.well-known/api-catalog",
                "describedby": [
                    {"href": "/metadata/index.json", "type": "application/json"}
                ],
                "item": items,
            }
        ]
    }


def stale_files(root: Path, generated: dict[Path, str | bytes]) -> list[str]:
    stale = []
    for relative, payload in generated.items():
        target = root / relative
        expected = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        if not target.exists() or target.read_bytes() != expected:
            stale.append(str(relative))
    return stale


def media_type(path: Path) -> str:
    name = str(path)
    if name.endswith(".jsonld"):
        return "application/ld+json"
    if name.endswith(".yaml"):
        return "application/yaml"
    if (
        name.endswith(".json")
        or name.endswith("api-catalog")
        or name.endswith("cpsv-ap")
    ):
        return "application/json"
    return "application/octet-stream"


def sha256_uri(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def text(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        candidate = value.get("en") or next(iter(value.values()), None)
        return str(candidate) if candidate else fallback
    if isinstance(value, str):
        return value
    return fallback


def humanize(value: str) -> str:
    return re.sub(r"[_-]+", " ", value).strip().capitalize()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


if __name__ == "__main__":
    raise SystemExit(main())
