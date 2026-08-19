#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
publisher_image='python:3.12-slim-trixie@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36'

mkdir -p "$root/output/sqlite/relay"
docker run --rm \
  --platform linux/amd64 \
  --user "$(id -u):$(id -g)" \
  --network none \
  --read-only \
  --tmpfs /tmp \
  --volume "$root:/workspace:ro" \
  --volume "$root/output/sqlite/relay:/workspace/output/sqlite/relay" \
  --workdir /workspace/generator \
  "$publisher_image" \
  python -c 'from pathlib import Path; from solmara_lab.publisher import publish_relay_sources; publish_relay_sources(Path(".."))'

