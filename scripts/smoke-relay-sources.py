#!/usr/bin/env python3
"""Probe Relay source lookups used by the live Notary smoke."""

from __future__ import annotations

import json
import os
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "smoke" / "relay-sources.json"


@dataclass(frozen=True)
class RelayProbe:
    name: str
    base_url_env: str
    default_base_url: str
    token_env: str
    purpose: str
    dataset: str
    entity: str
    filter_field: str
    filter_value: str
    fields: tuple[str, ...]


PURPOSE_CHILD = "https://id.registrystack.org/solmara/purpose/child-benefit-review"
PURPOSE_PENSION = "https://id.registrystack.org/solmara/purpose/pension-payment-review"
PURPOSE_VOUCHER = "https://id.registrystack.org/solmara/purpose/voucher-eligibility-review"
PURPOSE_LIVESTOCK = "https://id.registrystack.org/solmara/purpose/livestock-movement-control"

PROBES = (
    RelayProbe(
        "child civil birth",
        "SOLMARA_CRA_RELAY_URL",
        "http://127.0.0.1:4311",
        "CRA_CHILD_BENEFIT_SOURCE_RAW",
        PURPOSE_CHILD,
        "cra_civil",
        "civil_person",
        "id",
        "2300010248",
        ("birth_brn", "birth_date", "deceased", "observed_at"),
    ),
    RelayProbe(
        "citizen population status",
        "SOLMARA_NIA_RELAY_URL",
        "http://127.0.0.1:4312",
        "NIA_CITIZEN_SOURCE_RAW",
        "https://id.registrystack.org/solmara/purpose/citizen-self-service",
        "nia_population",
        "person",
        "id",
        "2300010248",
        ("identity_status", "alive", "observed_at"),
    ),
    RelayProbe(
        "child social membership",
        "SOLMARA_SRO_RELAY_URL",
        "http://127.0.0.1:4313",
        "SRO_CHILD_BENEFIT_SOURCE_RAW",
        PURPOSE_CHILD,
        "sro_social",
        "household_member",
        "uin",
        "2300010248",
        ("household_id", "observed_at"),
    ),
    RelayProbe(
        "child social household",
        "SOLMARA_SRO_RELAY_URL",
        "http://127.0.0.1:4313",
        "SRO_CHILD_BENEFIT_SOURCE_RAW",
        PURPOSE_CHILD,
        "sro_social",
        "household",
        "id",
        "HH-002317",
        ("poverty_band", "observed_at"),
    ),
    RelayProbe(
        "child programme enrollment",
        "SOLMARA_PROGRAMME_RELAY_URL",
        "http://127.0.0.1:4314",
        "PROGRAMME_CHILD_BENEFIT_SOURCE_RAW",
        PURPOSE_CHILD,
        "mosd_programme",
        "enrollment",
        "uin",
        "2300010248",
        ("duplicate_flag", "observed_at"),
    ),
    RelayProbe(
        "pension civil death",
        "SOLMARA_CRA_RELAY_URL",
        "http://127.0.0.1:4311",
        "CRA_PENSION_SOURCE_RAW",
        PURPOSE_PENSION,
        "cra_civil",
        "civil_person",
        "id",
        "2300109568",
        ("deceased", "death_drn", "observed_at"),
    ),
    RelayProbe(
        "pension case",
        "SOLMARA_SIPF_RELAY_URL",
        "http://127.0.0.1:4315",
        "SIPF_PENSION_SOURCE_RAW",
        PURPOSE_PENSION,
        "sipf_pensions",
        "pension_case",
        "pensioner_uin",
        "2300109568",
        ("payment_status", "survivor_eligible", "observed_at"),
    ),
    RelayProbe(
        "nagdi farmer voucher",
        "SOLMARA_NAGDI_RELAY_URL",
        "http://127.0.0.1:4316",
        "NAGDI_NOTARY_SOURCE_RAW",
        PURPOSE_VOUCHER,
        "nagdi_agriculture",
        "farmer_voucher",
        "id",
        "FR-1001",
        ("farmer_registered", "data_use_authorized", "voucher_not_redeemed", "observed_at"),
    ),
    RelayProbe(
        "nagdi livestock movement",
        "SOLMARA_NAGDI_RELAY_URL",
        "http://127.0.0.1:4316",
        "NAGDI_NOTARY_SOURCE_RAW",
        PURPOSE_LIVESTOCK,
        "nagdi_agriculture",
        "livestock_movement",
        "id",
        "FR-1001",
        ("registered_herd", "origin_district_not_quarantined_for_species", "observed_at"),
    ),
)


def main() -> int:
    load_dotenv(ROOT / ".env")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    for probe in PROBES:
        result = run_probe(probe)
        results.append(result)
        if result["status"] != "ok":
            failures.append(f"{probe.name}: {result['status']} ({result.get('detail', 'no detail')})")

    OUTPUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        for failure in failures:
            print(f"smoke-relay-sources: {failure}", file=sys.stderr)
        print(f"smoke-relay-sources: wrote {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
        return 1

    print(f"smoke-relay-sources: {len(PROBES)} Relay source probes passed; wrote {OUTPUT.relative_to(ROOT)}")
    return 0


def run_probe(probe: RelayProbe) -> dict[str, Any]:
    token = os.environ.get(probe.token_env, "")
    if not token:
        return {"name": probe.name, "status": "missing_token", "detail": probe.token_env}

    base_url = os.environ.get(probe.base_url_env, probe.default_base_url)
    params = {
        "limit": "2",
        "fields": ",".join(probe.fields),
        probe.filter_field: probe.filter_value,
    }
    url = joined_url(
        base_url,
        f"/v1/datasets/{probe.dataset}/entities/{probe.entity}/records",
        params,
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Data-Purpose": probe.purpose,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8.0) as response:
            body = parse_json(response.read())
            return validate_probe_body(probe, response.status, body)
    except urllib.error.HTTPError as error:
        return {
            "name": probe.name,
            "status": f"http_{error.code}",
            "detail": compact_error_body(parse_json(error.read())),
        }
    except Exception as error:
        return {"name": probe.name, "status": "request_failed", "detail": error.__class__.__name__}


def validate_probe_body(probe: RelayProbe, status: int, body: Any) -> dict[str, Any]:
    if status != 200:
        return {"name": probe.name, "status": f"http_{status}", "detail": "unexpected status"}
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return {"name": probe.name, "status": "invalid_body", "detail": "missing data array"}
    if len(rows) != 1:
        return {"name": probe.name, "status": "unexpected_row_count", "detail": str(len(rows))}
    row = rows[0] if isinstance(rows[0], dict) else {}
    missing_fields = [field for field in probe.fields if field not in row]
    if missing_fields:
        return {"name": probe.name, "status": "missing_fields", "detail": ",".join(missing_fields)}
    return {
        "name": probe.name,
        "status": "ok",
        "dataset": probe.dataset,
        "entity": probe.entity,
        "row_count": len(rows),
    }


def joined_url(base_url: str, path: str, params: dict[str, str]) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"


def parse_json(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"unparsed": raw.decode("utf-8", errors="replace")[:200]}


def compact_error_body(body: Any) -> str:
    if isinstance(body, dict):
        code = body.get("code")
        title = body.get("title")
        detail = body.get("detail")
        return "; ".join(str(part) for part in (code, title, detail) if part)
    return str(body)[:200]


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
        parts = shlex.split(raw_value, posix=True)
        os.environ[key] = parts[0] if parts else ""


if __name__ == "__main__":
    raise SystemExit(main())
