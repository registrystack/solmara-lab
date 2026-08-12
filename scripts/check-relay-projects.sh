#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
set -a
. "$root/versions.env"
set +a

cd "$root/generator"
uv run python -c 'from pathlib import Path; from solmara_lab.publisher import publish_relay_sources; publish_relay_sources(Path(".."))'

temporary_root=$(mktemp -d "$root/output/relay-check.XXXXXX")
cleanup() {
  rm -rf -- "$temporary_root"
}
trap cleanup EXIT HUP INT TERM

cd "$root"
for authority in cra nia mosd sipf nagdi; do
  project="relays/$authority"
  database="$root/output/sqlite/relay/$authority.sqlite"
  generated="$temporary_root/$authority-generated"
  package="$temporary_root/$authority-package"
  docker run --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$database:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$REGISTRY_RELAYCTL_IMAGE" \
    --json check "$project" --production >/dev/null
  docker run --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$database:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$REGISTRY_RELAYCTL_IMAGE" \
    --json generate "$project" --output "${generated#"$root/"}" >/dev/null
  docker run --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$database:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$REGISTRY_RELAYCTL_IMAGE" \
    --json test "$project" >/dev/null
  docker run --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$database:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$REGISTRY_RELAYCTL_IMAGE" \
    --json package "$project" --output "${package#"$root/"}" >/dev/null
done

printf '%s\n' 'relay-check: five production Relay projects passed check, generate, test, and package'
