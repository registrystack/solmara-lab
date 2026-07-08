#!/usr/bin/env sh
set -eu

if [ ! -f .env ]; then
  echo ".env is missing; run 'just gen-secrets' first" >&2
  exit 1
fi

compose_project_name="$(python3 scripts/compose_project_name.py)"
for compose in $(find . -maxdepth 1 -name 'compose.coolify*.yaml' -print | sort); do
  COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$compose_project_name}" \
  SOLMARA_RELAY_IMAGE="${SOLMARA_RELAY_IMAGE:-ghcr.io/registrystack/solmara-lab-relay@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_NOTARY_IMAGE="${SOLMARA_NOTARY_IMAGE:-ghcr.io/registrystack/solmara-lab-notary@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_POSTGRES_IMAGE="${SOLMARA_POSTGRES_IMAGE:-ghcr.io/registrystack/solmara-lab-postgres@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_STATIC_METADATA_IMAGE="${SOLMARA_STATIC_METADATA_IMAGE:-ghcr.io/registrystack/solmara-lab-static-metadata@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_HOME_IMAGE="${SOLMARA_HOME_IMAGE:-ghcr.io/registrystack/solmara-lab-home@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_PORTAL_IMAGE="${SOLMARA_PORTAL_IMAGE:-ghcr.io/registrystack/solmara-lab-portal@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  SOLMARA_SCENARIO_RUNNER_IMAGE="${SOLMARA_SCENARIO_RUNNER_IMAGE:-ghcr.io/registrystack/solmara-lab-scenario-runner@sha256:0000000000000000000000000000000000000000000000000000000000000000}" \
  docker compose --env-file versions.env --env-file .env -f "$compose" config >/dev/null
done
