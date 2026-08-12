#!/usr/bin/env python3
"""Assemble the closed, secret-free hosted authority provisioning payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

AUTHORITIES = ("cra", "nia", "mosd", "sipf", "nagdi")
EVIDENCE_CELLS = ("cra", "nia", "sro", "mosd-programme", "sipf", "nagdi")
GENERATOR_FILES = frozenset({"__init__.py", "generate.py", "publisher.py"})
RELAY_FILES = {
    "cra": frozenset(
        {
            "codelists/record-lifecycle.yaml",
            "expected-http.yaml",
            "fixture.sql",
            "governance/classification-review-rationale.md",
            "governance/classification-review.yaml",
            "governance/identifier-lifecycle.yaml",
            "governance/legal-basis.yaml",
            "governance/processing.dpv.yaml",
            "registry.yaml",
            "runtime.yaml",
        }
    ),
    "nia": frozenset(
        {
            "codelists/identity-status.yaml",
            "codelists/record-lifecycle.yaml",
            "codelists/sex.yaml",
            "expected-http.yaml",
            "fixture.sql",
            "governance/classification-review-rationale.md",
            "governance/classification-review.yaml",
            "governance/identifier-lifecycle.yaml",
            "governance/legal-basis.yaml",
            "governance/processing.dpv.yaml",
            "registry.yaml",
            "runtime.yaml",
        }
    ),
    "mosd": frozenset(
        {
            "codelists/record-lifecycle.yaml",
            "expected-http.yaml",
            "fixture.sql",
            "governance/classification-review-rationale.md",
            "governance/classification-review.yaml",
            "governance/identifier-lifecycle.yaml",
            "governance/legal-basis.yaml",
            "governance/processing.dpv.yaml",
            "registry.yaml",
            "runtime.yaml",
        }
    ),
    "sipf": frozenset(
        {
            "codelists/payment-status.yaml",
            "codelists/record-lifecycle.yaml",
            "expected-http.yaml",
            "fixture.sql",
            "governance/classification-review-rationale.md",
            "governance/classification-review.yaml",
            "governance/identifier-lifecycle.yaml",
            "governance/legal-basis.yaml",
            "governance/processing.dpv.yaml",
            "registry.yaml",
            "runtime.yaml",
        }
    ),
    "nagdi": frozenset(
        {
            "codelists/record-lifecycle.yaml",
            "expected-http.yaml",
            "fixture.sql",
            "governance/classification-review-rationale.md",
            "governance/classification-review.yaml",
            "governance/identifier-lifecycle.yaml",
            "governance/legal-basis.yaml",
            "governance/processing.dpv.yaml",
            "registry.yaml",
            "runtime.yaml",
        }
    ),
}
EVIDENCE_FILES = {
    "cra": frozenset(
        {
            "bundle/adapters/birth-extract.rhai",
            "bundle/adapters/relay-extract.rhai",
            "bundle/adapters/relay-prepare.rhai",
            "bundle/derivations/child-benefit.rhai",
            "bundle/derivations/deceased.rhai",
            "bundle/derivations/linked.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/child-benefit.yaml",
            "bundle/fixtures/citizen.yaml",
            "bundle/fixtures/pension.yaml",
            "bundle/queries/birth-evidence.sql",
            "bundle/schemas/birth-facts.schema.yaml",
            "bundle/schemas/birth-response.schema.yaml",
            "bundle/schemas/deceased-facts.schema.yaml",
            "bundle/schemas/deceased-response.schema.yaml",
            "bundle/schemas/linked-facts.schema.yaml",
            "bundle/schemas/linked-response.schema.yaml",
            "bundle/schemas/relay-adapter-parameters.schema.yaml",
            "runtime.yaml",
        }
    ),
    "nia": frozenset(
        {
            "bundle/adapters/sqlite-extract.rhai",
            "bundle/derivations/population-active.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/child-benefit.yaml",
            "bundle/fixtures/citizen.yaml",
            "bundle/queries/population-evidence.sql",
            "bundle/schemas/population-facts.schema.yaml",
            "bundle/schemas/population-response.schema.yaml",
            "runtime.yaml",
        }
    ),
    "sro": frozenset(
        {
            "bundle/adapters/sqlite-extract.rhai",
            "bundle/derivations/poverty-priority.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/child-benefit.yaml",
            "bundle/queries/poverty-evidence.sql",
            "bundle/schemas/poverty-facts.schema.yaml",
            "bundle/schemas/poverty-response.schema.yaml",
            "runtime.yaml",
        }
    ),
    "mosd-programme": frozenset(
        {
            "bundle/adapters/relay-extract.rhai",
            "bundle/adapters/relay-prepare.rhai",
            "bundle/derivations/not-enrolled.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/child-benefit.yaml",
            "bundle/schemas/facts.schema.yaml",
            "bundle/schemas/relay-adapter-parameters.schema.yaml",
            "bundle/schemas/response.schema.yaml",
            "runtime.yaml",
        }
    ),
    "sipf": frozenset(
        {
            "bundle/adapters/relay-extract.rhai",
            "bundle/adapters/relay-prepare.rhai",
            "bundle/derivations/pension-active.rhai",
            "bundle/derivations/survivor-eligible.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/pension.yaml",
            "bundle/fixtures/survivor.yaml",
            "bundle/schemas/pension-facts.schema.yaml",
            "bundle/schemas/pension-response.schema.yaml",
            "bundle/schemas/relay-adapter-parameters.schema.yaml",
            "bundle/schemas/survivor-facts.schema.yaml",
            "bundle/schemas/survivor-response.schema.yaml",
            "runtime.yaml",
        }
    ),
    "nagdi": frozenset(
        {
            "bundle/adapters/relay-extract.rhai",
            "bundle/adapters/relay-prepare.rhai",
            "bundle/derivations/livestock.rhai",
            "bundle/derivations/voucher.rhai",
            "bundle/evidence.yaml",
            "bundle/fixtures/livestock.yaml",
            "bundle/fixtures/voucher.yaml",
            "bundle/schemas/livestock-facts.schema.yaml",
            "bundle/schemas/livestock-response.schema.yaml",
            "bundle/schemas/relay-adapter-parameters.schema.yaml",
            "bundle/schemas/voucher-facts.schema.yaml",
            "bundle/schemas/voucher-response.schema.yaml",
            "runtime.yaml",
        }
    ),
}
MANIFEST_NAME = "manifest.json"
MANIFEST_KEYS = frozenset({"format", "files"})
SHA256_LENGTH = 64
SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "audit",
        "audits",
        "extracts",
        "secrets",
    }
)
FORBIDDEN_SUFFIXES = (
    ".db",
    ".jwk",
    ".jwk.json",
    ".jsonl",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
)


class AssetBuildError(RuntimeError):
    """Raised when the immutable provisioning payload cannot be trusted."""


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk_files(root: Path) -> set[str]:
    if root.is_symlink() or not root.is_dir():
        raise AssetBuildError("asset source is not a regular directory")
    files: set[str] = set()
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                raise AssetBuildError("asset source contains a symbolic link")
        for name in names:
            path = current_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise AssetBuildError("asset source contains a symbolic link")
            if not stat.S_ISREG(metadata.st_mode):
                raise AssetBuildError("asset source contains a non-regular file")
            files.add(path.relative_to(root).as_posix())
    return files


def _validate_exact_tree(root: Path, expected: frozenset[str]) -> None:
    if _walk_files(root) != set(expected):
        raise AssetBuildError("asset source inventory is not allowed")


def _copy_exact_tree(source: Path, destination: Path, files: frozenset[str]) -> None:
    if destination.exists():
        raise AssetBuildError("asset destination is not empty")
    for relative in sorted(files):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def _path_is_sensitive(relative: str, *, allow_seed: bool = False) -> bool:
    path = PurePosixPath(relative)
    lowered = tuple(part.lower() for part in path.parts)
    if any(part in FORBIDDEN_DIRECTORY_NAMES for part in lowered[:-1]):
        return True
    name = lowered[-1]
    if "secret" in name or "private" in name:
        return True
    if name.endswith(FORBIDDEN_SUFFIXES):
        return True
    return name.endswith(".sqlite") and not allow_seed


def _validate_generated_tree(root: Path, *, allow_seed: bool = False) -> None:
    files = _walk_files(root)
    if not files:
        raise AssetBuildError("generated asset tree is empty")
    for relative in files:
        if _path_is_sensitive(relative, allow_seed=allow_seed):
            raise AssetBuildError("generated asset tree contains a forbidden artifact")


def _manifest(root: Path) -> dict[str, object]:
    files: dict[str, str] = {}
    for relative in sorted(_walk_files(root)):
        if relative != MANIFEST_NAME:
            files[relative] = _digest(root / relative)
    if not files:
        raise AssetBuildError("asset payload is empty")
    return {"format": 1, "files": files}


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _strict_json(data: bytes) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise AssetBuildError("asset manifest contains duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeError, json.JSONDecodeError):
        raise AssetBuildError("asset manifest is invalid") from None


def verify_manifest(root: Path) -> None:
    """Verify the exact, canonical manifest and every payload file."""

    if root.is_symlink() or not root.is_dir():
        raise AssetBuildError("asset payload is unavailable")
    manifest_path = root / MANIFEST_NAME
    try:
        raw = manifest_path.read_bytes()
        manifest = _strict_json(raw)
        if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
            raise AssetBuildError("asset manifest shape is invalid")
        if manifest.get("format") != 1 or isinstance(manifest.get("format"), bool):
            raise AssetBuildError("asset manifest format is invalid")
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise AssetBuildError("asset manifest inventory is invalid")
        for relative, expected_digest in files.items():
            if (
                not isinstance(relative, str)
                or not relative
                or PurePosixPath(relative).is_absolute()
                or ".." in PurePosixPath(relative).parts
                or relative != PurePosixPath(relative).as_posix()
                or any(
                    not SAFE_PATH_COMPONENT.fullmatch(component)
                    for component in PurePosixPath(relative).parts
                )
                or relative == MANIFEST_NAME
                or not isinstance(expected_digest, str)
                or len(expected_digest) != SHA256_LENGTH
                or any(
                    character not in "0123456789abcdef" for character in expected_digest
                )
            ):
                raise AssetBuildError("asset manifest entry is invalid")
        observed = _manifest(root)
        if manifest != observed or raw != _manifest_bytes(observed):
            raise AssetBuildError("asset manifest verification failed")
    except AssetBuildError:
        raise
    except OSError:
        raise AssetBuildError("asset manifest verification failed") from None


def _validate_sources(root: Path) -> None:
    _validate_exact_tree(root / "generator" / "solmara_lab", GENERATOR_FILES)
    for authority in AUTHORITIES:
        _validate_exact_tree(root / "relays" / authority, RELAY_FILES[authority])
    for cell in EVIDENCE_CELLS:
        _validate_exact_tree(root / "evidence" / "cells" / cell, EVIDENCE_FILES[cell])
    mint = root / "evidence" / "mint.yaml"
    if mint.is_symlink() or not mint.is_file():
        raise AssetBuildError("Mint template is unavailable")


def _relay_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _prepare_packaging_project(project: Path, authority: str, seed: Path) -> None:
    shutil.copyfile(seed, project / "source.sqlite")
    runtime = project / "runtime.yaml"
    hosted_path = f"/var/lib/relay/source/{authority}.sqlite"
    content = runtime.read_text(encoding="utf-8")
    if content.count(hosted_path) != 1:
        raise AssetBuildError("Relay runtime source binding is unexpected")
    runtime.write_text(content.replace(hosted_path, "source.sqlite"), encoding="utf-8")


def build(root: Path, output: Path, relayctl: Path) -> None:
    """Build fresh Relay packages/sources and copy authored templates."""

    root = root.absolute()
    output = output.absolute()
    relayctl = relayctl.absolute()
    if output.exists() or output.is_symlink():
        raise AssetBuildError("asset destination already exists")
    if not relayctl.is_file() or relayctl.is_symlink():
        raise AssetBuildError("relayctl is unavailable")
    _validate_sources(root)

    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root / "generator"))
    from solmara_lab import publisher  # pylint: disable=import-outside-toplevel

    with tempfile.TemporaryDirectory(prefix="solmara-hosted-assets-") as temporary:
        staging = Path(temporary) / "assets"
        staging.mkdir()

        published = publisher.publish_relay_sources(staging)
        for authority in AUTHORITIES:
            project = Path(temporary) / "projects" / authority
            _copy_exact_tree(
                root / "relays" / authority, project, RELAY_FILES[authority]
            )
            _prepare_packaging_project(project, authority, published[authority])
            package = staging / "relays" / authority / "package"
            package.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    str(relayctl),
                    "--json",
                    "package",
                    str(project),
                    "--output",
                    str(package),
                ],
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=_relay_environment(),
            )
            _validate_generated_tree(package)
            runtime = staging / "relays" / authority / "runtime.yaml"
            shutil.copyfile(root / "relays" / authority / "runtime.yaml", runtime)
            seed = staging / "relays" / authority / "source" / f"{authority}.sqlite"
            seed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(published[authority], seed)

        for cell in EVIDENCE_CELLS:
            _copy_exact_tree(
                root / "evidence" / "cells" / cell,
                staging / "evidence" / "cells" / cell,
                EVIDENCE_FILES[cell],
            )
        mint = staging / "mint" / "mint.yaml"
        mint.parent.mkdir(parents=True)
        shutil.copyfile(root / "evidence" / "mint.yaml", mint)
        _copy_exact_tree(
            root / "generator" / "solmara_lab",
            staging / "generator" / "solmara_lab",
            GENERATOR_FILES,
        )

        manifest = _manifest(staging)
        (staging / MANIFEST_NAME).write_bytes(_manifest_bytes(manifest))
        verify_manifest(staging)
        shutil.copytree(staging, output)
        verify_manifest(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", choices=("build",))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--relayctl", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.root, args.output, args.relayctl)
    # This is the security redaction boundary. Neither dependency failures nor
    # relayctl diagnostics may disclose paths, configuration, or source values.
    except Exception:  # noqa: BLE001
        print("hosted runtime asset build failed", file=sys.stderr)
        return 1
    print("hosted runtime assets ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
