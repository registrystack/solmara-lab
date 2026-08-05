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
    echo "registryctl $required_version with project-authoring check/test/build/capabilities is required" >&2
    echo "set REGISTRYCTL_BIN to a compatible Registry Stack build" >&2
    exit 1
  fi
done
if ! "$REGISTRYCTL" tooling editor --help >/dev/null 2>&1; then
  echo "registryctl $required_version with project-authoring editor setup is required" >&2
  echo "set REGISTRYCTL_BIN to a compatible Registry Stack build" >&2
  exit 1
fi

projects="
cra-civil
nia-population
sro-social
mosd-programme
sipf-pensions
nagdi-agriculture
"

build_project_output() {
  project=$1
  environment=$2
  project_directory="$ROOT/projects/$project"
  echo "registryctl build: $project ($environment)" >&2
  build_report=$(
    "$REGISTRYCTL" build \
      --project-dir "$project_directory" \
      --environment "$environment" \
      --format json
  )
  printf '%s\n' "$build_report" |
    python3 "$ROOT/scripts/registryctl-build-output.py" \
      --project-dir "$project_directory" \
      --environment "$environment"
}

build_projects() {
  environment=$1
  for project in $projects; do
    build_project_output "$project" "$environment"
  done
}

check_projects() {
  detail=$1
  for project in $projects; do
    for environment in local hosted; do
      echo "registryctl check: $project ($environment)"
      if [ "$detail" = "explain" ]; then
        "$REGISTRYCTL" check \
          --project-dir "$ROOT/projects/$project" \
          --environment "$environment" \
          --explain
      else
        "$REGISTRYCTL" check \
          --project-dir "$ROOT/projects/$project" \
          --environment "$environment"
      fi
    done
  done
}

inspect_capabilities() {
  for project in $projects; do
    for environment in local hosted; do
      echo "registryctl capabilities: $project ($environment)"
      "$REGISTRYCTL" check \
        --project-dir "$ROOT/projects/$project" \
        --environment "$environment" \
        --explain
    done
  done
}

sync_editor_support() {
  for project in $projects; do
    echo "registryctl authoring editor: $project"
    "$REGISTRYCTL" tooling editor \
      --project-dir "$ROOT/projects/$project"
  done
}

stage_runtime() {
  destination=$1
  for environment in local hosted; do
    for project in $projects; do
      build_root=$(build_project_output "$project" "$environment")
      source="$build_root/private"
      target="$destination/$environment/$project"
      mkdir -p "$target/relay" "$target/relay-consultation"
      cp -R "$source/relay-public/config/." "$target/relay/"
      cp -R "$source/relay-consultation/config/." "$target/relay-consultation/"
    done
  done
  chmod -R u=rwX,go=rX "$destination"
}

action=${1:-}
case "$action" in
  test)
    for project in $projects; do
      for environment in local hosted; do
        echo "registryctl test: $project ($environment)"
        "$REGISTRYCTL" test \
          --project-dir "$ROOT/projects/$project" \
          --environment "$environment" \
          --format json |
          python3 "$ROOT/scripts/registryctl-test-output.py"
      done
    done
    ;;
  check)
    check_projects concise
    ;;
  review)
    check_projects explain
    ;;
  capabilities)
    inspect_capabilities
    ;;
  editor)
    sync_editor_support
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
    echo "usage: $0 <test|check|review|capabilities|editor|build <local|hosted>|sync-runtime|check-runtime>" >&2
    exit 2
    ;;
esac
