#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s <registry-stack-worktree>\n' "$0" >&2
  exit 2
fi

stack_dir="$(cd -- "$1" && pwd -P)"
commit="$(git -C "${stack_dir}" rev-parse HEAD)"
if [[ ! "${commit}" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Registry Stack HEAD must resolve to a lowercase 40-character commit SHA\n' >&2
  exit 1
fi
if [[ -n "$(git -C "${stack_dir}" status --porcelain)" ]]; then
  printf 'Registry Stack candidate worktree must be clean\n' >&2
  exit 1
fi

builder_image='rust:1.95-trixie@sha256:f49565f188ee00bc2a18dd418183f2c5f23ef7d6e691890517ed341a598f67c3'
relay_features="$(<"${stack_dir}/crates/registry-relay/canonical-release-features.txt")"
engine_arch="$(docker version --format '{{.Server.Arch}}')"
case "${engine_arch}" in
  amd64 | x86_64)
    relay_arch='amd64'
    ;;
  arm64 | aarch64)
    relay_arch='arm64'
    ;;
  *)
    printf 'unsupported Docker server architecture: %s\n' "${engine_arch}" >&2
    exit 1
    ;;
esac
relay_platform="linux/${relay_arch}"
image="registry-relay-opencrvs:${commit}-${relay_arch}"
image_version="0.15.2-opencrvs.${commit:0:12}"
linux_target="/workspace/target/opencrvs-linux-${relay_arch}"

cargo build --locked --manifest-path "${stack_dir}/Cargo.toml" \
  -p registryctl --bin registryctl

docker run --rm \
  --platform "${relay_platform}" \
  --user "$(id -u):$(id -g)" \
  --volume "${stack_dir}:/workspace" \
  --workdir /workspace \
  --env CARGO_HOME=/workspace/.cargo-home \
  --env CARGO_INCREMENTAL=0 \
  --env CARGO_TARGET_DIR="${linux_target}" \
  --env HOME=/workspace \
  --env REGISTRY_RELAY_FEATURES="${relay_features}" \
  "${builder_image}" \
  bash -c 'set -euo pipefail
    cargo build --release --locked \
      -p registry-relay \
      --no-default-features \
      --features "${REGISTRY_RELAY_FEATURES}"
    python3 release/scripts/check-release-relay-features.py \
      "${CARGO_TARGET_DIR}/release/registry-relay"
  '

mkdir -p "${stack_dir}/dist/image-bin"
install -m 0755 \
  "${stack_dir}/target/opencrvs-linux-${relay_arch}/release/registry-relay" \
  "${stack_dir}/dist/image-bin/registry-relay"
install -m 0755 \
  "${stack_dir}/target/opencrvs-linux-${relay_arch}/release/registry-relay-rhai-worker" \
  "${stack_dir}/dist/image-bin/registry-relay-rhai-worker"

docker buildx build \
  --load \
  --platform "${relay_platform}" \
  --file "${stack_dir}/release/docker/Dockerfile.registry-relay" \
  --tag "${image}" \
  --label 'org.opencontainers.image.source=https://github.com/registrystack/registry-stack' \
  --label "org.opencontainers.image.revision=${commit}" \
  --label "org.opencontainers.image.version=${image_version}" \
  --label "org.registrystack.registry-relay.features=${relay_features}" \
  --build-arg SOURCE_DATE_EPOCH=0 \
  "${stack_dir}"

image_architecture="$(
  docker image inspect --format '{{.Architecture}}' "${image}"
)"
image_revision="$(
  docker image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
    "${image}"
)"
image_features="$(
  docker image inspect \
    --format '{{index .Config.Labels "org.registrystack.registry-relay.features"}}' \
    "${image}"
)"
if [[ "${image_architecture}" != "${relay_arch}" ||
      "${image_revision}" != "${commit}" ||
      "${image_features}" != "${relay_features}" ]]; then
  printf 'candidate Relay image identity check failed\n' >&2
  exit 1
fi

printf "export OPENCRVS_DEMO_REGISTRYCTL='%s'\n" \
  "${stack_dir}/target/debug/registryctl"
printf "export OPENCRVS_DEMO_REGISTRYCTL_SOURCE_COMMIT='%s'\n" "${commit}"
printf "export OPENCRVS_DEMO_RELAY_IMAGE='%s'\n" "${image}"
printf "export OPENCRVS_DEMO_RELAY_SOURCE_COMMIT='%s'\n" "${commit}"
printf "export OPENCRVS_DEMO_RELAY_PLATFORM='%s'\n" "${relay_platform}"
