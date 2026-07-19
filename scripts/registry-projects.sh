#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
VERSION_FILE="$ROOT/versions.env"
REGISTRYCTL=${REGISTRYCTL_BIN:-}

required_version=$(sed -n 's/^REGISTRYCTL_VERSION=//p' "$VERSION_FILE")
if [ -z "$required_version" ]; then
  echo "versions.env must set REGISTRYCTL_VERSION" >&2
  exit 1
fi

if [ -z "$REGISTRYCTL" ]; then
  REGISTRYCTL=$("$ROOT/scripts/registryctl-pinned.sh" path)
fi
actual_version=$("$REGISTRYCTL" --version 2>/dev/null || true)
if [ "$actual_version" != "registryctl $required_version" ]; then
  echo "registryctl $required_version is required; got ${actual_version:-no executable}" >&2
  echo "set REGISTRYCTL_BIN to the matching release binary when it is not on PATH" >&2
  exit 1
fi
for command in check test build; do
  if ! "$REGISTRYCTL" "$command" --help >/dev/null 2>&1; then
    echo "registryctl $required_version with project-authoring check/test/build is required" >&2
    echo "set REGISTRYCTL_BIN to a compatible Registry Stack build" >&2
    exit 1
  fi
done

projects="
cra-civil
nia-population
sro-social
mosd-programme
sipf-pensions
nagdi-agriculture
"

build_projects() {
  environment=$1
  for project in $projects; do
    echo "registryctl build: $project ($environment)"
    "$REGISTRYCTL" build \
      --project-dir "$ROOT/projects/$project" \
      --environment "$environment"
  done
}

stage_runtime() {
  destination=$1
  for environment in local hosted; do
    build_projects "$environment"
    for project in $projects; do
      source="$ROOT/projects/$project/.registry-stack/build/$environment/private"
      target="$destination/$environment/$project"
      mkdir -p "$target/relay" "$target/notary"
      cp -R "$source/relay/config/." "$target/relay/"
      cp "$source/notary/config/notary.yaml" "$target/notary/notary.yaml"
    done
  done
  chmod -R u=rwX,go=rX "$destination"
}

action=${1:-}
case "$action" in
  test)
    for project in $projects; do
      echo "registryctl test: $project"
      "$REGISTRYCTL" test --project-dir "$ROOT/projects/$project"
    done
    ;;
  check)
    for project in $projects; do
      for environment in local hosted; do
        echo "registryctl check: $project ($environment)"
        "$REGISTRYCTL" check \
          --project-dir "$ROOT/projects/$project" \
          --environment "$environment"
      done
    done
    ;;
  build)
    environment=${2:-}
    case "$environment" in
      local | hosted) ;;
      *)
        echo "usage: $0 build <local|hosted>" >&2
        exit 2
        ;;
    esac
    build_projects "$environment"
    ;;
  sync-runtime)
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/solmara-registry-runtime.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    stage_runtime "$temporary/registry-projects"
    target="$ROOT/runtime/registry-projects"
    rm -rf "$target"
    mkdir -p "$(dirname "$target")"
    mv "$temporary/registry-projects" "$target"
    ;;
  check-runtime)
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/solmara-registry-runtime.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    stage_runtime "$temporary/registry-projects"
    diff -ruN "$ROOT/runtime/registry-projects" "$temporary/registry-projects"
    ;;
  *)
    echo "usage: $0 <test|check|build <local|hosted>|sync-runtime|check-runtime>" >&2
    exit 2
    ;;
esac
