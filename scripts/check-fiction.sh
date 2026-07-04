#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

forbidden=(
  "demo.example.gov"
  "country: ZZ"
  "Republic of Farajaland"
  "Philippines"
  "Philippine"
  "North District"
  "South District"
  "East District"
  "West District"
)

fail=0
for term in "${forbidden[@]}"; do
  if grep -RIn \
    --exclude-dir=.git \
    --exclude-dir=node_modules \
    --exclude-dir=.venv \
    --exclude-dir=.svelte-kit \
    --exclude-dir=build \
    --exclude-dir=output \
    --exclude-dir=test-results \
    --exclude='*.pyc' \
    --exclude='AGENTS.md' \
    --exclude='check-fiction.sh' \
    "$term" "$root" >/tmp/solmara-fiction-grep.txt; then
    echo "Forbidden legacy fiction found: $term" >&2
    cat /tmp/solmara-fiction-grep.txt >&2
    fail=1
  fi
done

if ! "$root/scripts/check-nid-aliases.py" > /tmp/solmara-nid-grep.txt 2>&1; then
  cat /tmp/solmara-nid-grep.txt >&2
  fail=1
fi

rm -f /tmp/solmara-fiction-grep.txt /tmp/solmara-nid-grep.txt
exit "$fail"
