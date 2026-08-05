#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "$#" -ne 0 ]; then
  echo "usage: scripts/review.sh" >&2
  exit 2
fi

"$root/scripts/check-fiction.sh"
"$root/scripts/check-image-pins.py"
"$root/scripts/check-config-secrets.py"
"$root/scripts/registry-projects.sh" check
"$root/scripts/registry-projects.sh" check-runtime
"$root/scripts/check-evidence-runtime.py"
uv run --project "$root" "$root/scripts/publish-metadata.py" --check
uv run --project "$root" "$root/scripts/metadata-lint.py"

if git -C "$root" grep -I -n \
  -E "(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{20,})" \
  -- .; then
  echo "Potential secret material found in repository files." >&2
  exit 1
fi

cat <<'CHECKLIST'
Security checklist for reviewer:
1. Purpose-gated Relay entities require Data-Purpose where sensitive data is exposed.
2. Evidence source credentials are short-lived Relay workload tokens held in a private runtime volume.
3. Mint authenticates the application with private_key_jwt and issues only the configured Evidence audience.
4. Evidence requirements disclose reviewed concept values as flattened signed JWS, never source rows.
5. Run `just smoke` against the live stack to exercise Mint, Evidence, Relay sources, scenarios, and the portal.
6. Audit and subject-binding secrets are generated locally and remain uncommitted.
7. The exact Registry Stack main commit in versions.env owns all three locally built runtime images.
CHECKLIST
