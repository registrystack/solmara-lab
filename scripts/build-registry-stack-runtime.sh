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

registry_stack_platform=${REGISTRY_STACK_PLATFORM:-linux/amd64}
if [ "$registry_stack_platform" != "linux/amd64" ]; then
  echo "published Registry Stack runtime assets require linux/amd64" >&2
  exit 1
fi
platform_args="--platform $registry_stack_platform"

verify_official_runtime() {
  component=$1
  image=$2
  expected_prefix="ghcr.io/registrystack/$component@sha256:"
  if ! printf '%s\n' "$image" | grep -Eq "^ghcr\\.io/registrystack/${component}@sha256:[0-9a-f]{64}$"; then
    echo "${component} runtime must use ${expected_prefix}<64 lowercase hex>" >&2
    exit 1
  fi

  pinned_digest=${image##*@}
  published_digest=$(
    docker buildx imagetools inspect \
      "ghcr.io/registrystack/${component}:v$version" \
      --format '{{.Manifest.Digest}}'
  )
  if [ "$published_digest" != "$pinned_digest" ]; then
    echo "published ${component} tag does not match the pinned digest" >&2
    exit 1
  fi

  docker pull "$image" >/dev/null
  revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image")
  image_version=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image")
  source=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.source" }}' "$image")
  if [ "$revision" != "$source_commit" ] || [ "$image_version" != "$version" ] || [ "$source" != "https://github.com/registrystack/registry-stack" ]; then
    echo "${component} runtime labels do not match the pinned Registry Stack release" >&2
    exit 1
  fi
}

verify_official_runtime relay "$relay_image"
verify_official_runtime evidence "$evidence_image"
verify_official_runtime mint "$mint_image"

build_relayctl() {
  image=$1
  current_revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image" 2>/dev/null || true)
  current_version=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$image" 2>/dev/null || true)
  current_architecture=$(docker image inspect --format '{{.Architecture}}' "$image" 2>/dev/null || true)
  if [ "$current_revision" = "$source_commit" ] && [ "$current_version" = "$version" ] && [ "$current_architecture" = "amd64" ]; then
    echo "relayctl image already matches Registry Stack v$version"
    return
  fi

  relayctl_context=$(mktemp -d)
  trap 'rm -rf -- "$relayctl_context"' EXIT HUP INT TERM
  relayctl_asset_file=${REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_FILE:-}
  if [ -n "$relayctl_asset_file" ]; then
    if [ -L "$relayctl_asset_file" ] || [ ! -f "$relayctl_asset_file" ]; then
      echo "provided Relayctl asset must be a regular file" >&2
      exit 1
    fi
    cp -- "$relayctl_asset_file" "$relayctl_context/relayctl"
  else
    curl --fail --location --silent --show-error \
      --retry 5 --retry-all-errors --connect-timeout 30 \
      --output "$relayctl_context/relayctl" \
      "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL"
  fi
  if [ -L "$relayctl_context/relayctl" ] || [ ! -f "$relayctl_context/relayctl" ]; then
    echo "downloaded Relayctl asset must be a regular file" >&2
    exit 1
  fi
  relayctl_sha256=$(sha256sum "$relayctl_context/relayctl" | awk '{print $1}')
  if [ "$relayctl_sha256" != "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" ]; then
    echo "downloaded Relayctl asset checksum does not match the release pin" >&2
    exit 1
  fi
  chmod 0755 "$relayctl_context/relayctl"

  # shellcheck disable=SC2086
  docker buildx build --load $platform_args \
    --label "org.opencontainers.image.source=https://github.com/registrystack/registry-stack" \
    --label "org.opencontainers.image.revision=$source_commit" \
    --label "org.opencontainers.image.version=$version" \
    --tag "$image" \
    --file "$root/docker/registry-stack-release-binary/Dockerfile" \
    --target relayctl \
    "$relayctl_context"
  rm -rf -- "$relayctl_context"
  trap - EXIT HUP INT TERM
}

build_relayctl "$relayctl_image"
