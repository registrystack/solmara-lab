#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
VERSION_FILE="$ROOT/versions.env"

version=$(sed -n 's/^REGISTRYCTL_VERSION=//p' "$VERSION_FILE")
if [ -z "$version" ]; then
  echo "versions.env must set REGISTRYCTL_VERSION" >&2
  exit 1
fi

verify_version() {
  actual=$("$1" --version 2>/dev/null || true)
  [ "$actual" = "registryctl $version" ]
}

if [ -n "${REGISTRYCTL_BIN:-}" ]; then
  if ! verify_version "$REGISTRYCTL_BIN"; then
    echo "REGISTRYCTL_BIN must point to registryctl $version" >&2
    exit 1
  fi
  registryctl=$REGISTRYCTL_BIN
elif command -v registryctl >/dev/null 2>&1 && verify_version "$(command -v registryctl)"; then
  registryctl=$(command -v registryctl)
else
  source_commit=$(sed -n 's/^REGISTRY_STACK_SOURCE_COMMIT=//p' "$VERSION_FILE")
  source_dir=${REGISTRY_STACK_SOURCE_DIR:-"$ROOT/../registry-stack"}
  if [ ! -d "$source_dir/.git" ]; then
    echo "REGISTRY_STACK_SOURCE_DIR must name a Registry Stack checkout" >&2
    exit 1
  fi
  actual_commit=$(git -C "$source_dir" rev-parse HEAD)
  if [ "$actual_commit" != "$source_commit" ]; then
    echo "Registry Stack source mismatch: expected $source_commit, found $actual_commit" >&2
    exit 1
  fi
  registryctl="$source_dir/target/release/registryctl"
  if ! verify_version "$registryctl"; then
    cargo build --locked --release --manifest-path "$source_dir/Cargo.toml" -p registryctl
  fi
  if ! verify_version "$registryctl"; then
    echo "the source-built registryctl did not report registryctl $version" >&2
    exit 1
  fi
fi

case "${1:-}" in
  path)
    [ "$#" -eq 1 ] || { echo "usage: $0 path" >&2; exit 2; }
    printf '%s\n' "$registryctl"
    ;;
  run)
    shift
    [ "$#" -gt 0 ] || { echo "usage: $0 run <registryctl arguments...>" >&2; exit 2; }
    exec "$registryctl" "$@"
    ;;
  *)
    echo "usage: $0 <path|run <registryctl arguments...>>" >&2
    exit 2
    ;;
esac
