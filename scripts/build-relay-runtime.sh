#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

set -a
# shellcheck disable=SC1091
. "$root/versions.env"
set +a

source_ref=${REGISTRY_STACK_SOURCE_REF:?missing REGISTRY_STACK_SOURCE_REF}
source_commit=${REGISTRY_STACK_SOURCE_COMMIT:?missing REGISTRY_STACK_SOURCE_COMMIT}
relay_features=${REGISTRY_RELAY_FEATURES:?missing REGISTRY_RELAY_FEATURES}
runtime_image=${SOLMARA_RELAY_RUNTIME_IMAGE:?missing SOLMARA_RELAY_RUNTIME_IMAGE}
release_image=${REGISTRY_RELAY_IMAGE:?missing REGISTRY_RELAY_IMAGE}
platform=${REGISTRY_STACK_PLATFORM:-linux/amd64}

case "$source_ref" in
  v[0-9]*.[0-9]*.[0-9]*) ;;
  *)
    echo "REGISTRY_STACK_SOURCE_REF must be a stable vMAJOR.MINOR.PATCH tag" >&2
    exit 1
    ;;
esac
case "$source_commit" in
  *[!0-9a-f]*)
    echo "REGISTRY_STACK_SOURCE_COMMIT must be exactly 40 lowercase hex characters" >&2
    exit 1
    ;;
esac
if [ "${#source_commit}" -ne 40 ]; then
  echo "REGISTRY_STACK_SOURCE_COMMIT must be exactly 40 lowercase hex characters" >&2
  exit 1
fi
case "$relay_features" in
  "" | *[!a-z0-9,-]*)
    echo "REGISTRY_RELAY_FEATURES must be a comma-separated lowercase feature list" >&2
    exit 1
    ;;
esac

image_revision=$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$runtime_image" 2>/dev/null || true
)
image_features=$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.registrystack.solmara.relay-features" }}' \
    "$runtime_image" 2>/dev/null || true
)
image_base=$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.base.name" }}' \
    "$runtime_image" 2>/dev/null || true
)
if [ "$image_revision" = "$source_commit" ] \
  && [ "$image_features" = "$relay_features" ] \
  && [ "$image_base" = "$release_image" ]; then
  echo "Solmara Relay runtime already matches $source_ref ($relay_features)"
  exit 0
fi

if [ -n "${REGISTRY_STACK_SOURCE_DIR:-}" ]; then
  source_dir=$REGISTRY_STACK_SOURCE_DIR
else
  source_dir="$root/.cache/registry-stack/$source_commit"
  if [ ! -d "$source_dir/.git" ]; then
    mkdir -p "$(dirname -- "$source_dir")"
    git clone --filter=blob:none --depth 1 --branch "$source_ref" \
      https://github.com/registrystack/registry-stack.git "$source_dir"
  fi
fi

actual_commit=$(git -C "$source_dir" rev-parse HEAD)
if [ "$actual_commit" != "$source_commit" ]; then
  echo "Registry Stack source mismatch: expected $source_commit, found $actual_commit" >&2
  exit 1
fi
if [ -n "$(git -C "$source_dir" status --porcelain)" ]; then
  echo "Registry Stack source checkout must be clean: $source_dir" >&2
  exit 1
fi

docker buildx build \
  --load \
  --platform "$platform" \
  --build-arg "REGISTRY_RELAY_IMAGE=$release_image" \
  --build-arg "REGISTRY_STACK_SOURCE_COMMIT=$source_commit" \
  --build-arg "REGISTRY_RELAY_FEATURES=$relay_features" \
  --tag "$runtime_image" \
  --file "$root/docker/relay-runtime/Dockerfile" \
  "$source_dir"
