#!/usr/bin/env python3
"""Regenerate the bounded eSignet identity fixture from canonical synthetic citizens."""

import argparse
import csv
from pathlib import Path
import uuid

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ROOT / "breg/population/dev-clients.yaml"
PERSON_REFERENCE_NAMESPACE = uuid.UUID("ae832c0a-a922-4f65-8c01-cc4a41d6c660")


def generated_seeds():
    with (ROOT / "ministries/interior-population/fixtures/population_person.csv").open() as source:
        rows = list(csv.DictReader(source))[:12]
    seeds = []
    for index, row in enumerate(rows, 1):
        seeds.append({
            "id": f"person-{index:02d}", "client": "operator", "entity": "person",
            "accessProfile": "operator", "data": {
                "uin": row["uin"], "status": row["identity_status"],
                "personReference": str(uuid.uuid5(PERSON_REFERENCE_NAMESPACE, row["uin"])),
                "givenName": row["given_name"], "familyName": row["family_name"],
                "birthdate": row["birth_date"], "gender": row["sex"],
                "operatorNote": "Synthetic seed; not disclosed to authentication provider.",
            },
        })
    seeds.append({
        "id": "inactive-person", "client": "operator", "entity": "person",
        "accessProfile": "operator", "data": {
            "uin": "2399999999", "status": "inactive",
            "personReference": str(uuid.uuid5(PERSON_REFERENCE_NAMESPACE, "2399999999")),
            "givenName": "Inactive", "familyName": "Fixture",
            "birthdate": "1980-01-01", "gender": "unknown",
            "operatorNote": "Synthetic seed; not disclosed to authentication provider.",
        },
    })
    return seeds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    clients = yaml.safe_load(CLIENTS.read_text())
    expected = generated_seeds()
    if args.check:
        if clients["seed"] != expected:
            raise SystemExit("BREG seeds differ from canonical synthetic citizens; regenerate explicitly")
        print("BREG seeds match canonical synthetic citizens")
        return
    clients["seed"] = expected
    CLIENTS.write_text(yaml.safe_dump(clients, sort_keys=False))


if __name__ == "__main__":
    main()
