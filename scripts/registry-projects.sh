#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
VERSION_FILE="$ROOT/versions.env"
REGISTRYCTL=${REGISTRYCTL_BIN:-registryctl}

required_version=$(sed -n 's/^REGISTRYCTL_VERSION=//p' "$VERSION_FILE")
if [ -z "$required_version" ]; then
  echo "versions.env must set REGISTRYCTL_VERSION" >&2
  exit 1
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
    for project in $projects; do
      echo "registryctl build: $project ($environment)"
      "$REGISTRYCTL" build \
        --project-dir "$ROOT/projects/$project" \
        --environment "$environment"
    done
    ;;
  *)
    echo "usage: $0 <test|check|build <local|hosted>>" >&2
    exit 2
    ;;
esac
