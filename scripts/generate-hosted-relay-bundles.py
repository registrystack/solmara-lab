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


def write_governed_config(
    source: Path,
    destination: Path,
    project: str,
) -> dict[str, object]:
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    container_dir = CONTAINER_ROOT / project
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


def generate_project(
    registryctl: str,
    project: str,
    private_jwk: Path,
    public_jwk: Path,
    sequence: int,
    output_root: Path,
) -> None:
    runtime_dir = ROOT / "runtime" / "registry-projects" / "hosted" / project / "relay"
    source_config = runtime_dir / "relay.yaml"
    if not source_config.is_file():
        raise SystemExit(f"missing hosted Relay config: {source_config}")

    instance_id = yaml.safe_load(source_config.read_text(encoding="utf-8"))[
        "instance"
    ]["id"]
    stream_id = f"solmara-hosted-{project}"
    project_output = output_root / project

    with tempfile.TemporaryDirectory(prefix=f"solmara-{project}-bundle-") as temporary:
        staging = Path(temporary)
        input_config = staging / "input" / "config"
        input_config.mkdir(parents=True)
        governed_config = input_config / "relay.yaml"
        write_governed_config(source_config, governed_config, project)
        artifacts = runtime_dir / "artifacts"
        if artifacts.exists():
            shutil.copytree(artifacts, input_config / "artifacts")

        bundle_dir = staging / "bundle"
        run(
            registryctl,
            "bundle",
            "sign",
            "--input",
            str(staging / "input"),
            "--key",
            str(private_jwk),
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
            f"solmara-hosted-{project}-sequence-{sequence}",
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
    parser.add_argument("--private-jwk", type=Path, required=True)
    parser.add_argument("--public-jwk", type=Path, required=True)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.sequence < 1:
        raise SystemExit("--sequence must be positive")
    for key_path in (args.private_jwk, args.public_jwk):
        if not key_path.is_file():
            raise SystemExit(f"missing signing key: {key_path}")
    private_jwk = json.loads(args.private_jwk.read_text(encoding="utf-8"))
    public_jwk = json.loads(args.public_jwk.read_text(encoding="utf-8"))
    if "d" not in private_jwk or "d" in public_jwk:
        raise SystemExit("expected a private JWK and a public-only JWK")
    if args.out.exists():
        raise SystemExit(f"output path must not exist: {args.out}")

    registryctl = registryctl_path()
    args.out.mkdir(parents=True)
    for project in PROJECTS:
        generate_project(
            registryctl,
            project,
            args.private_jwk,
            args.public_jwk,
            args.sequence,
            args.out,
        )
    for path in args.out.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
