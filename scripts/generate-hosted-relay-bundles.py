#!/usr/bin/env python3
"""Generate signed, instance-bound Relay bundles for hosted Solmara."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
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
)
CONTAINER_ROOT = Path("/etc/solmara/hosted-relay-bundles")
ANTIROLLBACK_PATH = (
    "/var/lib/registry-relay/cache/config-bundle-antirollback.json"
)


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def registryctl_path() -> str:
    result = subprocess.run(
        [str(ROOT / "scripts" / "registryctl-pinned.sh"), "path"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def configured_bundle_sequence() -> int:
    for raw_line in (ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("SOLMARA_RELAY_BUNDLE_SEQUENCE="):
            raw_sequence = raw_line.split("=", 1)[1]
            break
    else:
        raise SystemExit("versions.env must set SOLMARA_RELAY_BUNDLE_SEQUENCE")
    try:
        sequence = int(raw_sequence)
    except ValueError:
        raise SystemExit(
            "SOLMARA_RELAY_BUNDLE_SEQUENCE must be a positive integer"
        ) from None
    if sequence < 1:
        raise SystemExit("SOLMARA_RELAY_BUNDLE_SEQUENCE must be a positive integer")
    return sequence


def validate_private_jwk_reference(value: str) -> str:
    if value.startswith("op://"):
        if not value.removeprefix("op://").strip() or any(
            character in value for character in ("\r", "\n", "\0")
        ):
            raise SystemExit("invalid 1Password private JWK reference")
        return value

    key_path = Path(value)
    if not key_path.is_file():
        raise SystemExit(f"missing signing key: {key_path}")
    private_jwk = json.loads(key_path.read_text(encoding="utf-8"))
    if "d" not in private_jwk:
        raise SystemExit("expected a private JWK or op:// secret reference")
    return value


def validate_public_jwk(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"missing signing key: {path}")
    public_jwk = json.loads(path.read_text(encoding="utf-8"))
    if "d" in public_jwk:
        raise SystemExit("expected a public-only JWK")
    return path


def write_governed_config(
    source: Path,
    destination: Path,
    container_dir: Path,
) -> dict[str, object]:
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["config_trust"] = {
        "trust_anchor_path": str(container_dir / "trust-anchor.json"),
        "bundle_path": str(container_dir / "bundle"),
        "antirollback_state_path": ANTIROLLBACK_PATH,
    }
    destination.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    return config


def generate_bundle(
    registryctl: str,
    project: str,
    variant: str,
    source_name: str,
    output_subdirectory: str,
    include_artifacts: bool,
    private_jwk: str,
    public_jwk: Path,
    sequence: int,
    output_root: Path,
) -> None:
    runtime_dir = ROOT / "runtime" / "registry-projects" / "hosted" / project / "relay"
    source_config = runtime_dir / source_name
    if not source_config.is_file():
        raise SystemExit(f"missing hosted {variant} Relay config: {source_config}")

    source_document = yaml.safe_load(source_config.read_text(encoding="utf-8"))
    if variant == "public" and "consultation" in source_document:
        raise SystemExit(f"{project} public Relay config contains consultation authority")
    if variant == "consultation" and "consultation" not in source_document:
        raise SystemExit(f"{project} consultation Relay config omits consultation authority")
    instance_id = source_document["instance"]["id"]
    stream_suffix = "" if variant == "public" else "-consultation"
    stream_id = f"solmara-hosted-{project}{stream_suffix}"
    project_output = output_root / project
    container_dir = CONTAINER_ROOT / project
    if output_subdirectory:
        project_output /= output_subdirectory
        container_dir /= output_subdirectory

    with tempfile.TemporaryDirectory(
        prefix=f"solmara-{project}-{variant}-bundle-"
    ) as temporary:
        staging = Path(temporary)
        input_config = staging / "input" / "config"
        input_config.mkdir(parents=True)
        governed_config = input_config / "relay.yaml"
        write_governed_config(source_config, governed_config, container_dir)
        artifacts = runtime_dir / "artifacts"
        if include_artifacts:
            if not artifacts.is_dir():
                raise SystemExit(f"missing hosted consultation artifacts: {artifacts}")
            shutil.copytree(artifacts, input_config / "artifacts")

        bundle_dir = staging / "bundle"
        run(
            registryctl,
            "bundle",
            "sign",
            "--input",
            str(staging / "input"),
            "--key",
            private_jwk,
            "--product",
            "registry-relay",
            "--environment",
            "hosted",
            "--stream-id",
            stream_id,
            "--instance-id",
            instance_id,
            "--sequence",
            str(sequence),
            "--bundle-id",
            f"{stream_id}-sequence-{sequence}",
            "--out",
            str(bundle_dir),
        )

        anchor = staging / "trust-anchor.json"
        run(
            registryctl,
            "anchor",
            "init",
            "--anchor-path",
            str(anchor),
            "--product",
            "registry-relay",
            "--environment",
            "hosted",
            "--stream-id",
            stream_id,
            "--instance-id",
            instance_id,
        )
        run(
            registryctl,
            "anchor",
            "add-key",
            "--anchor-path",
            str(anchor),
            "--jwk-path",
            str(public_jwk),
        )
        run(
            registryctl,
            "bundle",
            "verify",
            "--bundle-dir",
            str(bundle_dir),
            "--anchor-path",
            str(anchor),
        )

        project_output.mkdir(parents=True)
        shutil.copy2(governed_config, project_output / "bootstrap.yaml")
        shutil.copy2(anchor, project_output / "trust-anchor.json")
        shutil.copytree(bundle_dir, project_output / "bundle")
        seed = {
            "key": {
                "product": "registry-relay",
                "environment": "hosted",
                "stream_id": stream_id,
            },
            "last_sequence": 0,
            "last_config_hash": f"sha256:{'0' * 64}",
        }
        (project_output / "antirollback-seed.json").write_text(
            json.dumps(seed, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-jwk",
        required=True,
        help="Private JWK path or op:// secret reference",
    )
    parser.add_argument("--public-jwk", type=Path, required=True)
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    configured_sequence = configured_bundle_sequence()
    sequence = args.sequence if args.sequence is not None else configured_sequence
    if sequence < 1:
        raise SystemExit("--sequence must be positive")
    if sequence != configured_sequence:
        raise SystemExit(
            "--sequence must match SOLMARA_RELAY_BUNDLE_SEQUENCE in versions.env"
        )
    private_jwk = validate_private_jwk_reference(args.private_jwk)
    public_jwk = validate_public_jwk(args.public_jwk)
    if args.out.exists():
        raise SystemExit(f"output path must not exist: {args.out}")

    registryctl = registryctl_path()
    args.out.mkdir(parents=True)
    for project in PROJECTS:
        for variant in BUNDLE_VARIANTS:
            generate_bundle(
                registryctl,
                project,
                *variant,
                private_jwk,
                public_jwk,
                sequence,
                args.out,
            )
    for path in args.out.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
