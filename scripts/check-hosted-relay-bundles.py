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
BUNDLE_VARIANTS = (
    ("public", "relay.yaml", "", False),
    ("consultation", "relay-consultation.yaml", "consultation", True),
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


def expected_bundle_sequence() -> int:
    for raw_line in (ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("SOLMARA_RELAY_BUNDLE_SEQUENCE="):
            raw_sequence = raw_line.split("=", 1)[1]
            break
    else:
        fail("versions.env must set SOLMARA_RELAY_BUNDLE_SEQUENCE")
    try:
        sequence = int(raw_sequence)
    except ValueError:
        fail("SOLMARA_RELAY_BUNDLE_SEQUENCE must be a positive integer")
    if sequence < 1:
        fail("SOLMARA_RELAY_BUNDLE_SEQUENCE must be a positive integer")
    return sequence


def load_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a mapping")
    return value


def regular_file_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir():
        fail(f"missing artifact directory {root}")
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            fail(f"artifact tree contains symlink {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f"artifact tree contains non-file {relative}")
        files[relative] = path.read_bytes()
    return files


def verify_artifact_closure(
    project: str, bundled_artifacts: Path, source_artifacts: Path
) -> None:
    bundled_files = regular_file_tree(bundled_artifacts)
    source_files = regular_file_tree(source_artifacts)
    if bundled_files.keys() != source_files.keys():
        fail(f"{project} signed artifact paths differ from compiler output")
    for relative, bundled_content in bundled_files.items():
        if bundled_content != source_files[relative]:
            fail(
                f"{project} signed artifact {relative} differs from compiler output"
            )


def main() -> int:
    registryctl = registryctl_path()
    expected_sequence = expected_bundle_sequence()
    for project in PROJECTS:
        for variant, source_name, output_subdirectory, include_artifacts in BUNDLE_VARIANTS:
            project_dir = BUNDLE_ROOT / project
            container_dir = CONTAINER_ROOT / project
            if output_subdirectory:
                project_dir /= output_subdirectory
                container_dir /= output_subdirectory
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
                / source_name
            )
            bundled_artifacts = bundle_dir / "config" / "artifacts"
            source_artifacts = source_config_path.parent / "artifacts"
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
            if variant == "public" and "consultation" in source:
                fail(f"{project} public Relay config contains consultation authority")
            if variant == "consultation" and "consultation" not in source:
                fail(f"{project} consultation Relay config omits consultation authority")
            if bootstrap != bundled:
                fail(
                    f"{project} {variant} bootstrap config differs from signed config"
                )

            expected_trust = {
                "trust_anchor_path": str(container_dir / "trust-anchor.json"),
                "bundle_path": str(container_dir / "bundle"),
                "antirollback_state_path": ANTIROLLBACK_PATH,
            }
            if bundled.get("config_trust") != expected_trust:
                fail(
                    f"{project} {variant} config trust paths are not deployment-bound"
                )
            unsigned_projection = copy.deepcopy(bundled)
            unsigned_projection.pop("config_trust", None)
            if unsigned_projection != source:
                fail(f"{project} {variant} signed config differs from compiler output")
            if include_artifacts:
                verify_artifact_closure(
                    f"{project} {variant}", bundled_artifacts, source_artifacts
                )
            elif bundled_artifacts.exists():
                fail(f"{project} public bundle contains private consultation artifacts")

            anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
            manifest = json.loads(
                (bundle_dir / "manifest.json").read_text(encoding="utf-8")
            )
            instance_id = source["instance"]["id"]
            stream_suffix = "" if variant == "public" else "-consultation"
            stream_id = f"solmara-hosted-{project}{stream_suffix}"
            expected_binding = {
                "product": "registry-relay",
                "environment": "hosted",
                "stream_id": stream_id,
                "instance_id": instance_id,
            }
            for key, expected in expected_binding.items():
                if anchor.get(key) != expected or manifest.get(key) != expected:
                    fail(f"{project} {variant} has an incorrect {key} binding")
            if manifest.get("sequence") != expected_sequence:
                fail(
                    f"{project} {variant} bundle sequence must match "
                    "SOLMARA_RELAY_BUNDLE_SEQUENCE"
                )
            if any(
                "d" in signer.get("jwk", {}) for signer in anchor.get("signers", [])
            ):
                fail(f"{project} {variant} trust anchor contains private key material")
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
                fail(
                    f"{project} {variant} anti-rollback seed is not "
                    "the sequence-zero baseline"
                )

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
