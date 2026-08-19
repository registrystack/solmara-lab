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
DATASET_DEFAULTS = {
    "cra-civil": {
        "concepts": [
            "https://publicschema.org/crvs/Birth",
            "https://publicschema.org/crvs/Death",
        ],
    },
    "nia-population": {
        "concepts": ["https://publicschema.org/Person"],
    },
    "sro-social": {
        "concepts": [
            "https://publicschema.org/Household",
            "https://publicschema.org/SocioEconomicProfile",
        ],
    },
    "mosd-programme": {
        "concepts": ["https://publicschema.org/sp/Enrollment"],
    },
    "sipf-pensions": {
        "concepts": ["https://id.registrystack.org/solmara/semantics/pension-case"],
    },
    "nagdi-agriculture": {
        "concepts": ["https://publicschema.org/Farm"],
    },
}

AUTHORITY_EVIDENCE_URLS = {
    "cra": "https://cra-evidence.solmara.registrystack.org",
    "nia": "https://nia-evidence.solmara.registrystack.org",
    "sro": "https://sro-evidence.solmara.registrystack.org",
    "mosd-programme-mis": "https://mosd-programme-evidence.solmara.registrystack.org",
    "sipf": "https://sipf-evidence.solmara.registrystack.org",
    "nagdi": "https://nagdi-evidence.solmara.registrystack.org",
}

EVIDENCE_OFFERING_SPECS = [
    {
        "id": "cra-child-benefit-v1-offering",
        "dataset": "cra-civil",
        "entity": "civil_person",
        "authority": "cra",
        "evidence_type": "cra-child-benefit-v1",
        "service": "child-benefit-review",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "lookup_keys": ["uin"],
        "concepts": [
            "https://id.registrystack.org/solmara/concept/birth-is-registered",
            "https://id.registrystack.org/solmara/concept/child-age-under-5",
        ],
        "source": "immutable extract",
    },
    {
        "id": "cra-pension-death-v1-offering",
        "dataset": "cra-civil",
        "entity": "civil_person",
        "authority": "cra",
        "evidence_type": "cra-death-status-v1",
        "service": "pension-survivor-review",
        "purposes": [PENSION_PAYMENT_PURPOSE],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/person-is-deceased"],
        "source": "Relay lookup",
    },
    {
        "id": "cra-citizen-record-v1-offering",
        "dataset": "cra-civil",
        "entity": "civil_person",
        "authority": "cra",
        "evidence_type": "civil-record-linked-v1",
        "service": "citizen-self-service",
        "purposes": ["https://id.registrystack.org/solmara/purpose/citizen-self-service"],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/civil-record-linked"],
        "source": "Relay lookup",
    },
    {
        "id": "nia-child-benefit-v1-offering",
        "dataset": "nia-population",
        "entity": "population_person",
        "authority": "nia",
        "evidence_type": "population-active-v1",
        "service": "child-benefit-review",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/population-record-active"],
        "source": "immutable extract",
    },
    {
        "id": "nia-citizen-status-v1-offering",
        "dataset": "nia-population",
        "entity": "population_person",
        "authority": "nia",
        "evidence_type": "citizen-population-active-v1",
        "service": "citizen-self-service",
        "purposes": ["https://id.registrystack.org/solmara/purpose/citizen-self-service"],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/citizen-population-record-active"],
        "source": "immutable extract",
    },
    {
        "id": "sro-child-benefit-v1-offering",
        "dataset": "sro-social",
        "entity": "poverty_record",
        "authority": "sro",
        "evidence_type": "poverty-priority-v1",
        "service": "child-benefit-review",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/household-below-poverty-threshold"],
        "source": "immutable extract",
    },
    {
        "id": "mosd-child-benefit-v1-offering",
        "dataset": "mosd-programme",
        "entity": "beneficiary_enrolment",
        "authority": "mosd-programme-mis",
        "evidence_type": "not-enrolled-v1",
        "service": "child-benefit-review",
        "purposes": [CHILD_BENEFIT_PURPOSE],
        "lookup_keys": ["uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/not-already-enrolled"],
        "source": "Relay lookup",
    },
    {
        "id": "sipf-pension-payment-v1-offering",
        "dataset": "sipf-pensions",
        "entity": "pension_payment",
        "authority": "sipf",
        "evidence_type": "pension-payment-active-v1",
        "service": "pension-survivor-review",
        "purposes": [PENSION_PAYMENT_PURPOSE],
        "lookup_keys": ["pensioner_uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/pension-payment-active"],
        "source": "Relay lookup",
    },
    {
        "id": "sipf-survivor-benefit-v1-offering",
        "dataset": "sipf-pensions",
        "entity": "survivor_case",
        "authority": "sipf",
        "evidence_type": "survivor-benefit-v1",
        "service": "pension-survivor-review",
        "purposes": [SURVIVOR_BENEFIT_PURPOSE],
        "lookup_keys": ["spouse_uin"],
        "concepts": ["https://id.registrystack.org/solmara/concept/survivor-is-eligible"],
        "source": "Relay lookup",
    },
    {
        "id": "nagdi-voucher-v1-offering",
        "dataset": "nagdi-agriculture",
        "entity": "farmer_voucher",
        "authority": "nagdi",
        "evidence_type": "climate-smart-voucher-v1",
        "service": "agriculture-review",
        "purposes": [VOUCHER_REVIEW_PURPOSE],
        "lookup_keys": ["farmer_id"],
        "concepts": [
            "https://id.registrystack.org/solmara/concept/farmer-registered",
            "https://id.registrystack.org/solmara/concept/data-use-authorized-for-purpose",
            "https://id.registrystack.org/solmara/concept/eligible-for-climate-smart-input-voucher",
        ],
        "source": "Relay lookup",
    },
    {
        "id": "nagdi-livestock-v1-offering",
        "dataset": "nagdi-agriculture",
        "entity": "livestock_movement",
        "authority": "nagdi",
        "evidence_type": "livestock-movement-v1",
        "service": "agriculture-review",
        "purposes": ["https://id.registrystack.org/solmara/purpose/livestock-movement-control"],
        "lookup_keys": ["farmer_id"],
        "concepts": [
            "https://id.registrystack.org/solmara/concept/registered-herd",
            "https://id.registrystack.org/solmara/concept/origin-district-not-quarantined-for-species",
            "https://id.registrystack.org/solmara/concept/eligible-for-livestock-movement-permit",
        ],
        "source": "Relay lookup",
    },
]

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
    datasets_by_id = {dataset["id"]: dataset for dataset in datasets}
    offerings = [
        authority_evidence_offering(spec, datasets_by_id, authorities)
        for spec in EVIDENCE_OFFERING_SPECS
    ]

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
    defaults = DATASET_DEFAULTS.get(dataset["id"], {})
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


def authority_evidence_offering(
    spec: dict[str, Any],
    datasets: dict[str, dict[str, Any]],
    authorities: dict[str, Any],
) -> dict[str, Any]:
    dataset = datasets[spec["dataset"]]
    authority = authorities[spec["authority"]]
    base_url = AUTHORITY_EVIDENCE_URLS[spec["authority"]]
    return {
        "id": spec["id"],
        "iri": f"https://id.registrystack.org/solmara/evidence-offerings/{spec['id']}",
        "title": f"{authority['name']} {humanize(spec['evidence_type'])}",
        "description": (
            f"An independently signed {spec['source']} assertion issued by "
            f"{authority['name']}."
        ),
        "dataset": dataset["id"],
        "entity": spec["entity"],
        "evidence_type": spec["evidence_type"],
        "issuing_authority": authority,
        "lookup_keys": spec["lookup_keys"],
        "public_services": [spec["service"]],
        "access": {
            "kind": "evidence-verification-api",
            "conforms_to": "https://id.registrystack.org/spec/registry-evidence/v1",
            "endpoint_url": f"{base_url}/v1/evidence",
            "discovery_url": f"{base_url}/v1/evidence-definitions",
            "source_type": spec["source"],
        },
        "purposes": spec["purposes"],
        "semantics": {
            "concepts": spec["concepts"],
            "application_profiles": ["cpsv-ap"],
        },
        "policy": f"{spec['id']}-policy",
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
