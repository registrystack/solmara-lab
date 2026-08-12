#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
set -a
. "$root/versions.env"
set +a

"$root/scripts/publish-relay-sources.sh"

temporary_root=$(mktemp -d "$root/output/relay-check.XXXXXX")
cleanup() {
  rm -rf -- "$temporary_root"
}
trap cleanup EXIT HUP INT TERM

cd "$root"
run_relayctl() {
  authority=$1
  database=$2
  stage=$3
  shift 3
  report="$temporary_root/$authority-$stage.json"
  if ! docker run --rm \
    --platform linux/amd64 \
    --user "$(id -u):$(id -g)" \
    --volume "$root:/workspace" \
    --volume "$database:/var/lib/relay/source/$authority.sqlite:ro" \
    --workdir /workspace \
    "$REGISTRY_RELAYCTL_IMAGE" \
    --json "$@" >"$report"; then
    printf 'relay-check: %s %s failed\n' "$authority" "$stage" >&2
    # relayctl diagnostics contain governed contract paths and error codes, not
    # selectors or source values. Preserve them so CI failures are actionable.
    cat "$report" >&2
    return 1
  fi
}

for authority in cra nia mosd sipf nagdi; do
  project="relays/$authority"
  database="$root/output/sqlite/relay/$authority.sqlite"
  generated="$temporary_root/$authority-generated"
  package="$temporary_root/$authority-package"
  run_relayctl "$authority" "$database" check \
    check "$project" --production
  run_relayctl "$authority" "$database" generate \
    generate "$project" --output "${generated#"$root/"}"
  run_relayctl "$authority" "$database" test \
    test "$project"
  run_relayctl "$authority" "$database" package \
    package "$project" --output "${package#"$root/"}"
done

printf '%s\n' 'relay-check: five production Relay projects passed check, generate, test, and package'
