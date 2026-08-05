#!/usr/bin/env sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

set -a
# shellcheck disable=SC1091
. "$root/versions.env"
set +a

source_ref=${REGISTRY_STACK_SOURCE_REF:?missing REGISTRY_STACK_SOURCE_REF}
source_commit=${REGISTRY_STACK_SOURCE_COMMIT:?missing REGISTRY_STACK_SOURCE_COMMIT}
relay_image=${REGISTRY_RELAY_IMAGE:?missing REGISTRY_RELAY_IMAGE}
evidence_image=${SOLMARA_EVIDENCE_IMAGE:?missing SOLMARA_EVIDENCE_IMAGE}
mint_image=${SOLMARA_MINT_IMAGE:?missing SOLMARA_MINT_IMAGE}
source_dir=${REGISTRY_STACK_SOURCE_DIR:-"$root/../registry-stack"}

if [ "$source_ref" != "main" ]; then
  echo "REGISTRY_STACK_SOURCE_REF must be main" >&2
  exit 1
fi
case "$source_commit" in
  *[!0-9a-f]*)
    echo "REGISTRY_STACK_SOURCE_COMMIT must be exactly 40 lowercase hex characters" >&2
    exit 1
    ;;
esac
if [ "${#source_commit}" -ne 40 ]; then
  echo "REGISTRY_STACK_SOURCE_COMMIT must be exactly 40 lowercase hex characters" >&2
  exit 1
fi
if [ ! -d "$source_dir/.git" ]; then
  echo "REGISTRY_STACK_SOURCE_DIR must name a Registry Stack checkout" >&2
  exit 1
fi
if ! git -C "$source_dir" cat-file -e "$source_commit^{commit}"; then
  echo "Registry Stack source commit is unavailable in $source_dir" >&2
  exit 1
fi
resolved_ref=$(git -C "$source_dir" rev-parse "$source_ref^{commit}")
remote_main=$(git -C "$source_dir" rev-parse "refs/remotes/origin/$source_ref^{commit}" 2>/dev/null || true)
if [ "$resolved_ref" != "$source_commit" ] || [ "$remote_main" != "$source_commit" ]; then
  echo "Registry Stack main does not match $source_commit; fetch origin/main and update versions.env intentionally" >&2
  exit 1
fi

all_current=true
for image in "$relay_image" "$evidence_image" "$mint_image"; do
  revision=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image" 2>/dev/null || true)
  if [ "$revision" != "$source_commit" ]; then
    all_current=false
  fi
done
if [ "$all_current" = true ]; then
  echo "Registry Stack runtime images already match $source_commit"
  exit 0
fi

temporary=$(mktemp -d "${TMPDIR:-/tmp}/solmara-registry-stack.XXXXXX")
worktree="$temporary/source"
cleanup() {
  git -C "$source_dir" worktree remove --force "$worktree" >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT HUP INT TERM
git -C "$source_dir" worktree add --detach "$worktree" "$source_commit" >/dev/null

platform_args=""
if [ -n "${REGISTRY_STACK_PLATFORM:-}" ]; then
  platform_args="--platform $REGISTRY_STACK_PLATFORM"
fi

# shellcheck disable=SC2086
docker buildx build --load $platform_args \
  --label "org.opencontainers.image.revision=$source_commit" \
  --label "org.opencontainers.image.ref.name=$source_ref" \
  --tag "$relay_image" \
  --file "$root/docker/registry-stack-runtime/Dockerfile" \
  --target relay \
  "$worktree"

for target in evidence mint; do
  case "$target" in
    evidence) image=$evidence_image ;;
    mint) image=$mint_image ;;
  esac
  # shellcheck disable=SC2086
  docker buildx build --load $platform_args \
    --label "org.opencontainers.image.revision=$source_commit" \
    --label "org.opencontainers.image.ref.name=$source_ref" \
    --tag "$image" \
    --file "$worktree/docker/Dockerfile" \
    --target "$target" \
    "$worktree"
done
