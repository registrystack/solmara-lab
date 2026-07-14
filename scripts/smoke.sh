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
  # The signing smokes need cryptography from the locked project environment.
  uv run --locked --project "$root" "$root/scripts/smoke-live.py"
  "$root/scripts/smoke-notary-state.sh"
  uv run --locked --project "$root" "$root/scripts/smoke-child-benefit-application.py"
  "$root/scripts/smoke-published-tokens.py"
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
