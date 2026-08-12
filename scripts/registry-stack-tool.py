#!/usr/bin/env python3
"""Download and verify pinned Registry Stack release binaries."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_BASE_URL = "https://github.com/registrystack/registry-stack/releases/download"
TOOLS = {"evidence", "evidencectl", "mint", "registryctl"}
PLATFORMS = {"linux-amd64", "linux-arm64", "macos-arm64"}


class ToolError(RuntimeError):
    """A pinned tool could not be selected or verified."""


def main(argv: list[str]) -> int:
    if len(argv) not in {3, 4} or argv[1] not in {"asset", "path"}:
        print(
            "usage: registry-stack-tool.py path <tool> | "
            "asset <tool> <linux-amd64|linux-arm64|macos-arm64>",
            file=sys.stderr,
        )
        return 2

    action, tool = argv[1:3]
    if tool not in TOOLS:
        print(f"unsupported Registry Stack tool: {tool}", file=sys.stderr)
        return 2

    try:
        if action == "path":
            if len(argv) != 3:
                raise ToolError("path selects the current host platform")
            selected_platform = host_platform()
        else:
            if len(argv) != 4 or argv[3] not in PLATFORMS:
                raise ToolError(
                    "asset requires linux-amd64, linux-arm64, or macos-arm64"
                )
            selected_platform = argv[3]

        versions = read_versions(ROOT / "versions.env")
        version = versions.get("REGISTRYCTL_VERSION", "")
        if not version:
            raise ToolError("versions.env must set REGISTRYCTL_VERSION")
        expected = expected_checksum(versions, tool, selected_platform)
        binary = cached_asset(tool, version, selected_platform, expected)
        if action == "path":
            verify_version(binary, tool, version)
        print(binary)
        return 0
    except ToolError as error:
        print(f"registry-stack-tool: {error}", file=sys.stderr)
        return 1


def host_platform() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    normalized_machine = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "amd64": "amd64",
        "x86_64": "amd64",
    }.get(machine)
    selected = {
        ("Linux", "amd64"): "linux-amd64",
        ("Linux", "arm64"): "linux-arm64",
        ("Darwin", "arm64"): "macos-arm64",
    }.get((system, normalized_machine or ""))
    if not selected:
        raise ToolError(f"unsupported host platform: {system} {machine}")
    return selected


def read_versions(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def expected_checksum(
    versions: dict[str, str], tool: str, selected_platform: str
) -> str:
    key = (
        f"REGISTRY_STACK_{tool.upper()}_"
        f"{selected_platform.upper().replace('-', '_')}_SHA256"
    )
    checksum = versions.get(key, "")
    if len(checksum) != 64 or any(
        character not in "0123456789abcdef" for character in checksum
    ):
        raise ToolError(f"versions.env must set {key} to 64 lowercase hex characters")
    return checksum


def cache_root() -> Path:
    override = os.environ.get("SOLMARA_REGISTRY_STACK_CACHE")
    if override:
        return Path(override)
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache) / "solmara-lab" / "registry-stack"
    return Path.home() / ".cache" / "solmara-lab" / "registry-stack"


def cached_asset(tool: str, version: str, selected_platform: str, expected: str) -> Path:
    name = f"{tool}-v{version}-{selected_platform}"
    destination = cache_root() / f"v{version}" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected:
        destination.chmod(0o755)
        return destination

    url = f"{RELEASE_BASE_URL}/v{version}/{name}"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{name}.", delete=False
        ) as temporary:
            temporary_name = temporary.name
            with urllib.request.urlopen(url, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
        temporary_path = Path(temporary_name)
        actual = sha256(temporary_path)
        if actual != expected:
            raise ToolError(
                f"checksum mismatch for {name}: expected {expected}, found {actual}"
            )
        temporary_path.chmod(0o755)
        temporary_path.replace(destination)
        temporary_name = None
    except urllib.error.HTTPError as error:
        raise ToolError(f"could not download {url}: HTTP {error.code}") from error
    except (OSError, urllib.error.URLError) as error:
        raise ToolError(f"could not download {url}: {error}") from error
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
    return destination


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as binary:
        while chunk := binary.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_version(binary: Path, tool: str, version: str) -> None:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ToolError(f"could not execute {binary.name} --version") from error
    expected = f"{tool} {version}"
    if completed.stdout.strip() != expected:
        raise ToolError(f"{binary.name} did not report {expected}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
