#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_digest=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
test_image="ghcr.io/registrystack/solmara-compose-check@sha256:$test_digest"

REGISTRY_STACK_RELEASE_RELAY_DIGEST="$test_digest" \
SOLMARA_EVIDENCE_IMAGE="$test_image" \
SOLMARA_MINT_IMAGE="$test_image" \
SOLMARA_STATIC_METADATA_IMAGE="$test_image" \
SOLMARA_SCENARIO_RUNNER_IMAGE="$test_image" \
SOLMARA_HOME_IMAGE="$test_image" \
SOLMARA_PORTAL_IMAGE="$test_image" \
docker compose \
  --env-file "$root/versions.env" \
  --env-file "$root/.env" \
  -f "$root/compose.yaml" \
  -f "$root/compose.hosted.yaml" \
  config >/dev/null
