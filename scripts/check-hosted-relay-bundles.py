#!/usr/bin/env python3
"""Verify committed hosted Relay bundles and their generated source closure."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = (
    "cra-civil",
    "nia-population",
    "sro-social",
    "mosd-programme",
    "sipf-pensions",
    "nagdi-agriculture",
)
BUNDLE_ROOT = ROOT / "config" / "hosted-relay-bundles"
CONTAINER_ROOT = Path("/etc/solmara/hosted-relay-bundles")
ANTIROLLBACK_PATH = (
    "/var/lib/registry-relay/cache/config-bundle-antirollback.json"
)


def fail(message: str) -> None:
    raise SystemExit(f"check-hosted-relay-bundles: {message}")


def registryctl_path() -> str:
    result = subprocess.run(
        [str(ROOT / "scripts" / "registryctl-pinned.sh"), "path"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def load_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a mapping")
    return value


def main() -> int:
    registryctl = registryctl_path()
    for project in PROJECTS:
        project_dir = BUNDLE_ROOT / project
        bootstrap_path = project_dir / "bootstrap.yaml"
        anchor_path = project_dir / "trust-anchor.json"
        seed_path = project_dir / "antirollback-seed.json"
        bundle_dir = project_dir / "bundle"
        bundle_config_path = bundle_dir / "config" / "relay.yaml"
        source_config_path = (
            ROOT
            / "runtime"
            / "registry-projects"
            / "hosted"
            / project
            / "relay"
            / "relay.yaml"
        )
        for required in (
            bootstrap_path,
            anchor_path,
            seed_path,
            bundle_dir / "manifest.json",
            bundle_dir / "manifest.sig.json",
            bundle_config_path,
            source_config_path,
        ):
            if not required.is_file():
                fail(f"missing {required.relative_to(ROOT)}")

        bootstrap = load_yaml(bootstrap_path)
        bundled = load_yaml(bundle_config_path)
        source = load_yaml(source_config_path)
        if bootstrap != bundled:
            fail(f"{project} bootstrap config differs from signed config")

        container_dir = CONTAINER_ROOT / project
        expected_trust = {
            "trust_anchor_path": str(container_dir / "trust-anchor.json"),
            "bundle_path": str(container_dir / "bundle"),
            "antirollback_state_path": ANTIROLLBACK_PATH,
        }
        if bundled.get("config_trust") != expected_trust:
            fail(f"{project} config trust paths are not deployment-bound")
        unsigned_projection = copy.deepcopy(bundled)
        unsigned_projection.pop("config_trust", None)
        if unsigned_projection != source:
            fail(f"{project} signed config differs from compiler output")

        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
        manifest = json.loads(
            (bundle_dir / "manifest.json").read_text(encoding="utf-8")
        )
        instance_id = source["instance"]["id"]
        stream_id = f"solmara-hosted-{project}"
        expected_binding = {
            "product": "registry-relay",
            "environment": "hosted",
            "stream_id": stream_id,
            "instance_id": instance_id,
        }
        for key, expected in expected_binding.items():
            if anchor.get(key) != expected or manifest.get(key) != expected:
                fail(f"{project} has an incorrect {key} binding")
        if not isinstance(manifest.get("sequence"), int) or manifest["sequence"] < 1:
            fail(f"{project} must use a positive bundle sequence")
        if any("d" in signer.get("jwk", {}) for signer in anchor.get("signers", [])):
            fail(f"{project} trust anchor contains private key material")
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        expected_seed = {
            "key": {
                "product": "registry-relay",
                "environment": "hosted",
                "stream_id": stream_id,
            },
            "last_sequence": 0,
            "last_config_hash": f"sha256:{'0' * 64}",
        }
        if seed != expected_seed:
            fail(f"{project} anti-rollback seed is not the sequence-zero baseline")

        subprocess.run(
            [
                registryctl,
                "bundle",
                "verify",
                "--bundle-dir",
                str(bundle_dir),
                "--anchor-path",
                str(anchor_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    print("check-hosted-relay-bundles: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
