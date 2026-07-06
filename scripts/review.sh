#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$root/scripts/check-fiction.sh"
"$root/scripts/check-image-pins.py"
"$root/scripts/check-release-pins.py" v0.8.4
"$root/scripts/check-config-secrets.py"
uv run --project "$root" "$root/scripts/publish-metadata.py" --check
uv run --project "$root" "$root/scripts/metadata-lint.py"

if grep -RIn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=ssl \
  -E "(BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{20,})" "$root"; then
  echo "Potential secret material found in repository files." >&2
  exit 1
fi

cat <<'CHECKLIST'
Security checklist for reviewer:
1. Purpose-gated Relay entities require Data-Purpose where sensitive data is exposed.
2. Raw tokens appear only in generated .env, never committed configs.
3. Notary source connections use token_env and scoped Relay tokens.
4. Redactable fields are not disclosed through predicate channels.
5. Federation smokes cover success, replay denial, and unsupported-purpose denial.
6. Audit hash secrets are environment-backed.
7. Fiction lint is green.
CHECKLIST
