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
  case "$(uname -s):$(uname -m)" in
    Linux:x86_64) platform=linux-amd64 ;;
    Linux:aarch64 | Linux:arm64) platform=linux-arm64 ;;
    Darwin:arm64) platform=macos-arm64 ;;
    *)
      echo "registryctl $version has no published binary for $(uname -s) $(uname -m)" >&2
      echo "set REGISTRYCTL_BIN to a verified compatible binary" >&2
      exit 1
      ;;
  esac

  asset="registryctl-v${version}-${platform}"
  tools="$ROOT/output/tools"
  registryctl="$tools/$asset"
  if ! verify_version "$registryctl"; then
    mkdir -p "$tools"
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/solmara-registryctl.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    base="https://github.com/registrystack/registry-stack/releases/download/v${version}"
    curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
      "$base/SHA256SUMS" -o "$temporary/SHA256SUMS"
    curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
      "$base/$asset" -o "$temporary/$asset"
    expected=$(awk -v asset="$asset" '$2 == asset { print $1 }' "$temporary/SHA256SUMS")
    if [ -z "$expected" ]; then
      echo "SHA256SUMS does not cover $asset" >&2
      exit 1
    fi
    if command -v sha256sum >/dev/null 2>&1; then
      actual=$(sha256sum "$temporary/$asset" | awk '{print $1}')
    else
      actual=$(shasum -a 256 "$temporary/$asset" | awk '{print $1}')
    fi
    if [ "$actual" != "$expected" ]; then
      echo "downloaded $asset failed its published SHA-256 check" >&2
      exit 1
    fi
    chmod 0755 "$temporary/$asset"
    mv "$temporary/$asset" "$registryctl"
    if ! verify_version "$registryctl"; then
      echo "downloaded $asset did not report registryctl $version" >&2
      exit 1
    fi
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
