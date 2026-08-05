#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$root/output/smoke"

ran=0
"$root/scripts/smoke-story-previews.py"
ran=1

if [ "${SOLMARA_SMOKE_LIVE:-1}" != "0" ]; then
  ran=1
  "$root/scripts/smoke-relay-sources.py"
  compose=(
    docker compose
    --env-file "$root/versions.env"
    --env-file "$root/.env"
    -f "$root/compose.yaml"
  )
  nia_esignet_relay_token=$(
    "${compose[@]}" exec -T nia-workload-agent \
      cat /run/esignet-secrets/solmara-esignet-relay-token
  )
  NIA_ESIGNET_RELAY_TOKEN="$nia_esignet_relay_token" \
    "$root/scripts/smoke-nia-attribute-release.py"
  unset nia_esignet_relay_token
  # The Mint private_key_jwt smoke needs cryptography from the locked environment.
  uv run --locked --project "$root" "$root/scripts/smoke-live.py"
  "$root/scripts/smoke-portal-compose.py"
fi

for script in "$root"/scripts/stories/*.sh; do
  if [ -x "$script" ]; then
    ran=1
    "$script"
  fi
done

if [ "$ran" -eq 0 ]; then
  echo "No story smoke scripts are installed yet." >&2
  exit 1
fi
