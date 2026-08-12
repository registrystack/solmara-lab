#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  exit 64
fi

template=$1
output=$2

validate_host() {
  candidate=$1
  [ -n "$candidate" ] || return 1
  [ "${#candidate}" -le 253 ] || return 1
  printf '%s\n' "$candidate" | awk -F. '
    NF < 2 { exit 1 }
    {
      for (i = 1; i <= NF; i++) {
        if (length($i) < 1 || length($i) > 63 ||
            $i !~ /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/) {
          exit 1
        }
      }
    }
  '
}

if ! validate_host "${SOLMARA_ESIGNET_PUBLIC_HOST:-}" ||
   ! validate_host "${SOLMARA_ESIGNET_UI_PUBLIC_HOST:-}"; then
  echo "eSignet hosted nginx host configuration is invalid" >&2
  exit 78
fi

# The validated values contain only lower-case DNS hostname characters. This
# makes these two literal substitutions safe in nginx directive and CSP slots.
sed \
  -e "s/__ESIGNET_PUBLIC_HOST__/${SOLMARA_ESIGNET_PUBLIC_HOST}/g" \
  -e "s/__ESIGNET_UI_PUBLIC_HOST__/${SOLMARA_ESIGNET_UI_PUBLIC_HOST}/g" \
  "$template" >"$output"
