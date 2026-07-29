#!/usr/bin/env python3
"""Verify Registry Stack release inputs match a published release tag."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE_KEYS = {
    "REGISTRY_RELAY_IMAGE": "ghcr.io/registrystack/registry-relay",
    "REGISTRY_NOTARY_IMAGE": "ghcr.io/registrystack/registry-notary",
}
REGISTRY_STACK_REMOTE = "https://github.com/registrystack/registry-stack.git"
PIN_RE = re.compile(r"^(?P<image>[^@\s]+)@(?P<digest>sha256:[0-9a-f]{64})$")
DIGEST_RE = re.compile(r"^Digest:\s+(sha256:[0-9a-f]{64})$", re.MULTILINE)
TAG_RE = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1]:
        print("usage: check-release-pins.py <registry-stack-tag>", file=sys.stderr)
        return 2

    tag = argv[1]
    if not TAG_RE.fullmatch(tag):
        print(
            "check-release-pins: tag must match "
            "vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-PRERELEASE",
            file=sys.stderr,
        )
        return 2

    versions = read_versions(ROOT / "versions.env")
    failures: list[str] = []
    release_version = tag.removeprefix("v")

    registryctl_version = versions.get("REGISTRYCTL_VERSION")
    if registryctl_version != release_version:
        failures.append(
            "REGISTRYCTL_VERSION from versions.env "
            f"is {registryctl_version or 'missing'}, expected {release_version}"
        )

    source_ref = versions.get("REGISTRY_STACK_SOURCE_REF")
    if source_ref != tag:
        failures.append(
            "REGISTRY_STACK_SOURCE_REF from versions.env "
            f"is {source_ref or 'missing'}, expected {tag}"
        )
    source_commit = versions.get("REGISTRY_STACK_SOURCE_COMMIT")
    if not source_commit or not COMMIT_RE.fullmatch(source_commit):
        failures.append(
            "REGISTRY_STACK_SOURCE_COMMIT must be exactly 40 lowercase hex characters"
        )

    for key in IMAGE_KEYS:
        pinned = versions.get(key)
        override = os.environ.get(key)
        if pinned and override and override != pinned:
            failures.append(f"{key} environment override must match versions.env")

    if failures:
        for failure in failures:
            print(f"check-release-pins: {failure}", file=sys.stderr)
        return 1

    try:
        tag_commit = resolve_tag_commit(tag)
    except (RuntimeError, subprocess.CalledProcessError):
        print(
            f"check-release-pins: could not resolve Registry Stack tag {tag}",
            file=sys.stderr,
        )
        return 1
    if source_commit != tag_commit:
        print(
            "check-release-pins: REGISTRY_STACK_SOURCE_COMMIT from versions.env "
            f"is {source_commit}, but {tag} resolves to {tag_commit}",
            file=sys.stderr,
        )
        return 1

    for key, image in IMAGE_KEYS.items():
        pinned = versions.get(key)
        if not pinned:
            failures.append(f"{key} is missing from versions.env")
            continue
        match = PIN_RE.match(pinned)
        if not match:
            failures.append(f"{key} must be image@sha256:<digest>")
            continue
        if match.group("image") != image:
            failures.append(f"{key} points at {match.group('image')}, expected {image}")
            continue
        release_digest = inspect_tag_digest(f"{image}:{tag}")
        if release_digest != match.group("digest"):
            failures.append(
                f"{key} from versions.env pins {match.group('digest')}, "
                f"but {image}:{tag} resolves to {release_digest}"
            )

    if failures:
        for failure in failures:
            print(f"check-release-pins: {failure}", file=sys.stderr)
        return 1

    print(f"check-release-pins: Registry Stack release inputs match {tag}")
    return 0


def read_versions(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def inspect_tag_digest(ref: str) -> str:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", ref],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    match = DIGEST_RE.search(result.stdout)
    if not match:
        raise RuntimeError(f"could not find digest in `docker buildx imagetools inspect {ref}` output")
    return match.group(1)


def resolve_tag_commit(tag: str) -> str:
    direct_ref = f"refs/tags/{tag}"
    peeled_ref = f"{direct_ref}^{{}}"
    result = subprocess.run(
        ["git", "ls-remote", REGISTRY_STACK_REMOTE, direct_ref, peeled_ref],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    refs: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        fields = raw_line.split()
        if len(fields) != 2 or fields[1] not in {direct_ref, peeled_ref}:
            raise RuntimeError("Registry Stack tag lookup returned an invalid ref")
        commit, ref = fields
        if ref in refs or not COMMIT_RE.fullmatch(commit):
            raise RuntimeError("Registry Stack tag lookup returned an invalid commit")
        refs[ref] = commit

    commit = refs.get(peeled_ref) or refs.get(direct_ref)
    if not commit:
        raise RuntimeError("Registry Stack tag lookup returned no matching tag")
    return commit


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
