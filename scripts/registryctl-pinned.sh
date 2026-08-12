#!/bin/sh
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
registryctl=$("$ROOT/scripts/registry-stack-tool.py" path registryctl)

case "${1:-}" in
  path)
    [ "$#" -eq 1 ] || { echo "usage: $0 path" >&2; exit 2; }
    printf '%s\n' "$registryctl"
    ;;
  run)
    shift
    [ "$#" -gt 0 ] || { echo "usage: $0 run <registryctl arguments...>" >&2; exit 2; }
    exec "$registryctl" "$@"
    ;;
  *)
    echo "usage: $0 <path|run <registryctl arguments...>>" >&2
    exit 2
    ;;
esac
