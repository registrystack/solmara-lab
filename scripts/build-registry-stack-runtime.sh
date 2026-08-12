#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

set -a
# shellcheck disable=SC1091
. "$root/versions.env"
set +a

"$root/scripts/check-registry-stack-release-pin.py" --require-public

version=${REGISTRY_STACK_REQUIRED_VERSION:?missing REGISTRY_STACK_REQUIRED_VERSION}
source_commit=${REGISTRY_STACK_SOURCE_COMMIT:?missing REGISTRY_STACK_SOURCE_COMMIT}
relay_digest=${REGISTRY_STACK_RELEASE_RELAY_DIGEST:?missing REGISTRY_STACK_RELEASE_RELAY_DIGEST}
relay_image=${REGISTRY_RELAY_IMAGE:?missing REGISTRY_RELAY_IMAGE}
relayctl_image=${REGISTRY_RELAYCTL_IMAGE:?missing REGISTRY_RELAYCTL_IMAGE}
evidence_image=${SOLMARA_EVIDENCE_IMAGE:?missing SOLMARA_EVIDENCE_IMAGE}
mint_image=${SOLMARA_MINT_IMAGE:?missing SOLMARA_MINT_IMAGE}

expected_relay="ghcr.io/registrystack/relay@sha256:$relay_digest"
if [ "$relay_image" != "$expected_relay" ]; then
  echo "REGISTRY_RELAY_IMAGE must bind the published Relay digest" >&2
  exit 1
fi
observed_relay=$(docker buildx imagetools inspect "ghcr.io/registrystack/relay:v$version" --format '{{.Manifest.Digest}}')
if [ "$observed_relay" != "sha256:$relay_digest" ]; then
  echo "published Relay tag does not match the required digest" >&2
  exit 1
fi

registry_stack_platform=${REGISTRY_STACK_PLATFORM:-linux/amd64}
if [ "$registry_stack_platform" != "linux/amd64" ]; then
  echo "published Registry Stack runtime assets require linux/amd64" >&2
  exit 1
fi
platform_args="--platform $registry_stack_platform"

build_release_binary() {
  target=$1
  image=$2
  current_revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image" 2>/dev/null || true)
  current_version=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image" 2>/dev/null || true)
  current_architecture=$(docker image inspect --format '{{.Architecture}}' "$image" 2>/dev/null || true)
  if [ "$current_revision" = "$source_commit" ] && [ "$current_version" = "$version" ] && [ "$current_architecture" = "amd64" ]; then
    echo "$target image already matches Registry Stack v$version"
    return
  fi

  # shellcheck disable=SC2086
  docker buildx build --load $platform_args \
    --build-arg "REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL=$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL" \
    --build-arg "REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256=$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256" \
    --build-arg "REGISTRY_STACK_RELEASE_MINT_ASSET_URL=$REGISTRY_STACK_RELEASE_MINT_ASSET_URL" \
    --build-arg "REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256=$REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256" \
    --build-arg "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL=$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL" \
    --build-arg "REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256=$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" \
    --label "org.opencontainers.image.source=https://github.com/registrystack/registry-stack" \
    --label "org.opencontainers.image.revision=$source_commit" \
    --label "org.opencontainers.image.version=$version" \
    --tag "$image" \
    --file "$root/docker/registry-stack-release-binary/Dockerfile" \
    --target "$target" \
    "$root"
}

build_release_binary evidence "$evidence_image"
build_release_binary mint "$mint_image"
build_release_binary relayctl "$relayctl_image"
