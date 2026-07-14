#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose --env-file "$root/versions.env" --env-file "$root/.env" -f "$root/compose.yaml")

notaries=(
  "civil-child-benefit-notary:/etc/registry-notary/child-benefit-civil.yaml"
  "nia-child-benefit-notary:/etc/registry-notary/child-benefit-population.yaml"
  "sro-child-benefit-notary:/etc/registry-notary/child-benefit-social.yaml"
  "programme-child-benefit-notary:/etc/registry-notary/child-benefit-programme.yaml"
  "pension-notary:/etc/registry-notary/pension.yaml"
  "nagdi-notary:/etc/registry-notary/nagdi.yaml"
  "citizen-notary:/etc/registry-notary/citizen.yaml"
)

if "${compose[@]}" --profile wallet ps --status running --services | grep -qx citizen-issuer-notary; then
  notaries+=("citizen-issuer-notary:/etc/registry-notary/citizen-issuer.yaml")
fi

for target in "${notaries[@]}"; do
  service=${target%%:*}
  config=${target#*:}
  "${compose[@]}" --profile wallet run --rm --no-deps "$service" \
    --config "$config" state doctor >/dev/null
  printf 'notary-state: %s ready\n' "$service"
done
