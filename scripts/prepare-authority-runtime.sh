#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
relayctl_image=${REGISTRY_RELAYCTL_IMAGE:-solmara-lab-relayctl:source}

cd "$root/generator"
uv run python -c 'from pathlib import Path; from solmara_lab.publisher import publish_relay_sources; publish_relay_sources(Path(".."))'

cd "$root"
uv run scripts/publish-runtime-extracts.py

for authority in cra nia mosd sipf nagdi; do
  destination="$root/relays/$authority/package"
  temporary_root=$(mktemp -d "$root/relays/$authority/.package.XXXXXX")
  temporary="$temporary_root/package"
  cleanup() {
    rm -rf "$temporary_root"
  }
  trap cleanup EXIT HUP INT TERM
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$root/output/sqlite/relay/$authority.sqlite:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$relayctl_image" \
    --json package "relays/$authority" --output "${temporary#"$root/"}" >/dev/null
  rm -rf "$destination"
  mv "$temporary" "$destination"
  rmdir "$temporary_root"
  trap - EXIT HUP INT TERM
done
