#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
project_name=${COMPOSE_PROJECT_NAME:-$(python3 "$root/scripts/compose_project_name.py")}

compose() {
  COMPOSE_PROJECT_NAME="$project_name" docker compose \
    --env-file "$root/versions.env" \
    --env-file "$root/.env" \
    -f "$root/compose.yaml" "$@"
}

for cell in cra nia sro mosd-programme sipf nagdi; do
  compose exec -T "$cell-evidence" evidence check \
    --runtime "/etc/registry-evidence/$cell/runtime.yaml"
  for fixture in "$root/runtime/evidence-cells/cells/$cell/bundle/fixtures/"*.yaml; do
    compose exec -T "$cell-evidence" evidence evaluate \
      --runtime "/etc/registry-evidence/$cell/runtime.yaml" \
      --fixture "fixtures/$(basename "$fixture")"
  done
done

printf '%s\n' 'evidence-check: six authority cells and all eleven requirement fixtures passed'
