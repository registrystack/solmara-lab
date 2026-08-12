#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

set -a
# shellcheck disable=SC1091
. "$root/versions.env"
set +a

version=${REGISTRYCTL_VERSION:?missing REGISTRYCTL_VERSION}
source_ref=${REGISTRY_STACK_SOURCE_REF:?missing REGISTRY_STACK_SOURCE_REF}
source_commit=${REGISTRY_STACK_SOURCE_COMMIT:?missing REGISTRY_STACK_SOURCE_COMMIT}
relay_image=${REGISTRY_RELAY_IMAGE:?missing REGISTRY_RELAY_IMAGE}
evidence_image=${SOLMARA_EVIDENCE_IMAGE:?missing SOLMARA_EVIDENCE_IMAGE}
mint_image=${SOLMARA_MINT_IMAGE:?missing SOLMARA_MINT_IMAGE}

if [ "$source_ref" != "v$version" ]; then
  echo "REGISTRY_STACK_SOURCE_REF must match v$version" >&2
  exit 1
fi
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
case "$relay_image" in
  ghcr.io/registrystack/registry-relay@sha256:*) ;;
  *)
    echo "REGISTRY_RELAY_IMAGE must pin the published Relay image by sha256 digest" >&2
    exit 1
    ;;
esac
relay_digest=${relay_image#ghcr.io/registrystack/registry-relay@sha256:}
case "$relay_digest" in
  *[!0-9a-f]*)
    echo "REGISTRY_RELAY_IMAGE must pin the published Relay image by sha256 digest" >&2
    exit 1
    ;;
esac
if [ "${#relay_digest}" -ne 64 ]; then
  echo "REGISTRY_RELAY_IMAGE must pin the published Relay image by sha256 digest" >&2
  exit 1
fi

target_platform=${REGISTRY_STACK_PLATFORM:-}
if [ -z "$target_platform" ]; then
  docker_arch=$(docker version --format '{{.Server.Arch}}')
  case "$docker_arch" in
    amd64 | x86_64) target_platform=linux/amd64 ;;
    arm64 | aarch64) target_platform=linux/arm64 ;;
    *)
      echo "unsupported Docker server architecture: $docker_arch" >&2
      exit 1
      ;;
  esac
fi
case "$target_platform" in
  linux/amd64) asset_platform=linux-amd64 ;;
  linux/arm64) asset_platform=linux-arm64 ;;
  *)
    echo "REGISTRY_STACK_PLATFORM must be linux/amd64 or linux/arm64" >&2
    exit 1
    ;;
esac

temporary=$(mktemp -d "${TMPDIR:-/tmp}/solmara-registry-stack-runtime.XXXXXX")
cleanup() {
  rm -rf "$temporary"
}
trap cleanup EXIT HUP INT TERM

mkdir -p \
  "$temporary/evidence-root/etc/registry-evidence" \
  "$temporary/evidence-root/var/lib/registry-evidence/audit" \
  "$temporary/mint-root/etc/registry-mint"

for target in evidence mint; do
  case "$target" in
    evidence) image=$evidence_image ;;
    mint) image=$mint_image ;;
  esac

  binary=$("$root/scripts/registry-stack-tool.py" asset "$target" "$asset_platform")
  install -m 0755 "$binary" "$temporary/$target"

  revision=$(docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$image" 2>/dev/null || true)
  image_version=$(docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' \
    "$image" 2>/dev/null || true)
  if [ "$revision" != "$source_commit" ] || [ "$image_version" != "$version" ]; then
    docker buildx build --load \
      --platform "$target_platform" \
      --label "org.opencontainers.image.revision=$source_commit" \
      --label "org.opencontainers.image.ref.name=$source_ref" \
      --label "org.opencontainers.image.version=$version" \
      --tag "$image" \
      --file "$root/docker/registry-stack-runtime/Dockerfile" \
      --target "$target" \
      "$temporary"
  fi

  actual=$(docker run --rm --platform "$target_platform" --entrypoint "/usr/local/bin/$target" "$image" --version)
  if [ "$actual" != "$target $version" ]; then
    echo "$image did not report $target $version" >&2
    exit 1
  fi
done

echo "Registry Stack Evidence and Mint runtime images match $source_ref; Relay uses $relay_image"
