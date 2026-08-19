#!/usr/bin/env python3
"""Publish and bind fresh immutable extracts in the generated local runtime."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generator"))
publisher = importlib.import_module("solmara_lab.publisher")

AUTHORITIES = {
    "cra": ("cra-birth-extract", "cra-birth"),
    "nia": ("nia-population-extract", "nia-population"),
    "sro": ("sro-poverty-extract", "sro-poverty"),
}
RUNTIME_DIRECTORY = Path("runtime/evidence-cells/cells")


class RuntimeExtractError(RuntimeError):
    """Raised when runtime publication or binding cannot be completed safely."""


def current_publication_time() -> str:
    return publisher.canonical_published_at(datetime.now(UTC).isoformat())


def _runtime_path(root: Path, authority: str) -> Path:
    return root / RUNTIME_DIRECTORY / authority / "runtime.yaml"


def _load_binding(runtime_path: Path, authority: str) -> tuple[str, str]:
    profile, prefix = AUTHORITIES[authority]
    try:
        document = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
        source_extracts = document["sourceExtracts"]
        if set(source_extracts) != {profile}:
            raise RuntimeExtractError("generated runtime has an unexpected extract profile")
        binding = source_extracts[profile]
        if set(binding) != {"path"} or not isinstance(binding["path"], str):
            raise RuntimeExtractError("generated runtime has an invalid extract binding")
    except RuntimeExtractError:
        raise
    except (KeyError, OSError, TypeError, UnicodeError, yaml.YAMLError):
        raise RuntimeExtractError("generated runtime cannot be validated") from None

    container_path = PurePosixPath(binding["path"])
    expected_parent = PurePosixPath(
        f"/var/lib/registry-evidence/{authority}/extracts"
    )
    if (
        container_path.parent != expected_parent
        or not container_path.name.startswith(prefix + "-")
        or not container_path.name.endswith(".sqlite")
    ):
        raise RuntimeExtractError("generated runtime has an invalid extract binding")
    return binding["path"], container_path.stem


def _render_binding(
    runtime_path: Path, old_container_path: str, new_container_path: str
) -> bytes:
    original = runtime_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?<![^\s{{]){re.escape(old_container_path)}(?=[\s}}])")
    rendered, replacements = pattern.subn(new_container_path, original)
    if replacements != 1:
        raise RuntimeExtractError("generated runtime binding is not uniquely patchable")
    return rendered.encode("utf-8")


def _replace_read_only_file(path: Path, content: bytes) -> None:
    directory = path.parent
    original_directory_mode = stat.S_IMODE(directory.stat().st_mode)
    original_file_mode = stat.S_IMODE(path.stat().st_mode)
    directory.chmod(original_directory_mode | stat.S_IWUSR)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=directory
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(original_file_mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        directory.chmod(original_directory_mode)


def prepare_runtime_extracts(
    root: Path = ROOT, published_at: str | None = None
) -> dict[str, dict[str, str]]:
    """Select fresh extracts, publish missing replacements, and bind generated cells."""

    root = root.resolve()
    publication_time = publisher.canonical_published_at(
        published_at if published_at is not None else current_publication_time()
    )
    planned: dict[str, dict[str, object]] = {}

    # Validate every existing binding and every possible target before writing
    # any file. A malformed or writable extract therefore leaves all bindings
    # on their previously reviewed values.
    for authority in AUTHORITIES:
        runtime_path = _runtime_path(root, authority)
        old_container_path, bound_extract_id = _load_binding(runtime_path, authority)
        bound_path = publisher.extract_path(root, bound_extract_id)
        selected_id = bound_extract_id
        selected_path = bound_path
        status = "reused"
        if bound_path.exists() or bound_path.is_symlink():
            try:
                publisher.validate_extract(
                    bound_path,
                    authority,
                    observed_at=publication_time,
                    expected_extract_id=bound_extract_id,
                )
            except publisher.StaleExtractError:
                status = "published"
            except publisher.ExtractValidationError as error:
                raise RuntimeExtractError(
                    f"{authority} bound extract failed validation: {error}"
                ) from None
        else:
            status = "published"

        if status == "published":
            selected_id = publisher.timestamped_extract_id(
                authority, publication_time
            )
            selected_path = publisher.extract_path(root, selected_id)
            if selected_path.exists() or selected_path.is_symlink():
                try:
                    publisher.validate_extract(
                        selected_path,
                        authority,
                        observed_at=publication_time,
                        expected_extract_id=selected_id,
                        expected_published_at=publication_time,
                    )
                except publisher.ExtractValidationError as error:
                    raise RuntimeExtractError(
                        f"{authority} publication target failed validation: {error}"
                    ) from None
                status = "recovered"

        new_container_path = str(
            PurePosixPath(old_container_path).with_name(selected_path.name)
        )
        planned[authority] = {
            "runtime_path": runtime_path,
            "old_container_path": old_container_path,
            "new_container_path": new_container_path,
            "selected_id": selected_id,
            "selected_path": selected_path,
            "status": status,
        }

    rendered = {
        authority: _render_binding(
            plan["runtime_path"],
            str(plan["old_container_path"]),
            str(plan["new_container_path"]),
        )
        for authority, plan in planned.items()
        if plan["old_container_path"] != plan["new_container_path"]
    }

    for authority, plan in planned.items():
        if plan["status"] != "published":
            continue
        selected_path = publisher.publish_extract(
            root, authority, publication_time, str(plan["selected_id"])
        )
        publisher.validate_extract(
            selected_path,
            authority,
            observed_at=publication_time,
            expected_extract_id=str(plan["selected_id"]),
            expected_published_at=publication_time,
        )

    for authority, content in rendered.items():
        _replace_read_only_file(Path(planned[authority]["runtime_path"]), content)

    return {
        authority: {
            "extractId": str(plan["selected_id"]),
            "path": str(Path(plan["selected_path"]).relative_to(root)),
            "status": str(plan["status"]),
        }
        for authority, plan in planned.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish and bind fresh immutable Evidence extracts"
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--published-at",
        help="explicit RFC 3339 publication time; defaults to the current UTC time",
    )
    args = parser.parse_args()
    result = prepare_runtime_extracts(args.root, args.published_at)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
