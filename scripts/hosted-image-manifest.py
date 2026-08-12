#!/usr/bin/env python3
"""Build and validate the sanitized image handoff for hosted Solmara deployments."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_REPOSITORIES = (
    ("SOLMARA_EVIDENCE_IMAGE", "solmara-lab-evidence"),
    ("SOLMARA_MINT_IMAGE", "solmara-lab-mint"),
    (
        "SOLMARA_AUTHORITY_PROVISIONER_IMAGE",
        "solmara-lab-authority-provisioner",
    ),
    ("SOLMARA_TRANSIT_SIGNER_IMAGE", "solmara-lab-transit-signer"),
    ("SOLMARA_STATIC_METADATA_IMAGE", "solmara-lab-static-metadata"),
    ("SOLMARA_SCENARIO_RUNNER_IMAGE", "solmara-lab-scenario-runner"),
    ("SOLMARA_HOME_IMAGE", "solmara-lab-home"),
    ("SOLMARA_PORTAL_IMAGE", "solmara-lab-portal"),
    ("SOLMARA_ESIGNET_RELAY_IMAGE", "solmara-lab-esignet-relay"),
    ("SOLMARA_ESIGNET_POSTGRES_IMAGE", "solmara-lab-esignet-postgres"),
    ("SOLMARA_ESIGNET_UI_IMAGE", "solmara-lab-esignet-ui"),
    ("SOLMARA_ESIGNET_SEED_IMAGE", "solmara-lab-esignet-seed"),
)
EXPECTED_KEYS = tuple(key for key, _repository in IMAGE_REPOSITORIES)
EXPECTED_REPOSITORIES = dict(IMAGE_REPOSITORIES)
MANIFEST_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=([^\s#]+)$")
HOSTED_IMAGE_LINE_RE = re.compile(
    r"^\s*image:\s*\$\{(SOLMARA_[A-Z0-9_]+_IMAGE):\?[^}]+\}\s*(?:#.*)?$"
)
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """A hosted image handoff violates its closed contract."""


def expected_reference(key: str, digest: str) -> str:
    repository = EXPECTED_REPOSITORIES[key]
    return f"ghcr.io/registrystack/{repository}@sha256:{digest}"


def validate_reference(key: str, value: str) -> None:
    prefix = expected_reference(key, "")
    if not value.startswith(prefix):
        raise ManifestError(
            f"{key} must reference {prefix}<64 lowercase hex>"
        )
    digest = value.removeprefix(prefix)
    if DIGEST_RE.fullmatch(digest) is None:
        raise ManifestError(
            f"{key} must be a full ghcr.io image@sha256:<64 lowercase hex> reference"
        )


def parse_manifest(text: str) -> dict[str, str]:
    if not text.endswith("\n"):
        raise ManifestError("manifest must end with one newline")
    if "\r" in text:
        raise ManifestError("manifest must use LF line endings")

    values: dict[str, str] = {}
    keys: list[str] = []
    for line_number, line in enumerate(text[:-1].split("\n"), start=1):
        match = MANIFEST_LINE_RE.fullmatch(line)
        if match is None:
            raise ManifestError(
                f"line {line_number} must contain exactly NAME=image@sha256:<64 hex>"
            )
        key, value = match.groups()
        if key in values:
            raise ManifestError(f"line {line_number} duplicates {key}")
        if key not in EXPECTED_REPOSITORIES:
            raise ManifestError(f"line {line_number} contains unexpected key {key}")
        validate_reference(key, value)
        values[key] = value
        keys.append(key)

    missing = [key for key in EXPECTED_KEYS if key not in values]
    if missing:
        raise ManifestError(f"manifest is missing {', '.join(missing)}")
    if tuple(keys) != EXPECTED_KEYS:
        raise ManifestError("manifest keys are not in canonical order")
    return values


def render_manifest(environment: Mapping[str, str]) -> str:
    missing = [key for key in EXPECTED_KEYS if not environment.get(key)]
    if missing:
        raise ManifestError(f"environment is missing {', '.join(missing)}")

    text = "".join(f"{key}={environment[key]}\n" for key in EXPECTED_KEYS)
    parse_manifest(text)
    return text


def read_manifest(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def hosted_compose_paths(root: Path) -> tuple[Path, ...]:
    return (root / "compose.hosted.yaml", *sorted(root.glob("compose.coolify*.yaml")))


def validate_hosted_compose_inventory(root: Path) -> None:
    paths = hosted_compose_paths(root)
    missing_files = [path.name for path in paths if not path.is_file()]
    if missing_files:
        raise ManifestError(f"hosted Compose file is missing: {', '.join(missing_files)}")

    observed: set[str] = set()
    malformed: list[str] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "image:" not in line or "${SOLMARA_" not in line:
                continue
            match = HOSTED_IMAGE_LINE_RE.fullmatch(line)
            if match is None:
                malformed.append(f"{path.name}:{line_number}")
                continue
            observed.add(match.group(1))

    if malformed:
        raise ManifestError(
            "hosted SOLMARA image references must be required variables: "
            + ", ".join(malformed)
        )

    expected = set(EXPECTED_KEYS)
    if observed != expected:
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        detail: list[str] = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected {', '.join(unexpected)}")
        raise ManifestError("hosted Compose image inventory mismatch: " + "; ".join(detail))


def write_manifest(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(text)
        temporary.flush()
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o644)
    temporary_path.replace(path)


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "--compose-root",
        type=Path,
        default=ROOT,
        help="repository root containing hosted Compose files",
    )
    subparsers = argument_parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write", help="write a canonical manifest from the environment")
    write.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="validate an existing canonical manifest")
    validate.add_argument("--manifest", type=Path, required=True)
    subparsers.add_parser("inventory", help="validate the hosted Compose image inventory")
    return argument_parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        validate_hosted_compose_inventory(arguments.compose_root)
        if arguments.command == "write":
            text = render_manifest(os.environ)
            write_manifest(arguments.output, text)
            parse_manifest(read_manifest(arguments.output))
        elif arguments.command == "validate":
            parse_manifest(read_manifest(arguments.manifest))
    except (ManifestError, OSError, UnicodeError) as error:
        print(f"hosted image manifest: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
