set dotenv-load
set positional-arguments

compose_project_name := `python3 scripts/compose_project_name.py`

default:
    @just --list

setup:
    uv sync
    cd generator && uv sync
    cd portal && pnpm install --frozen-lockfile
    cd home && pnpm install --frozen-lockfile

# Generate deterministic fixtures plus ignored operator/runtime material.
generate:
    cd generator && uv run python -m solmara_lab.generate
    uv run scripts/gen-secrets.py
    @if test -d runtime/evidence-cells; then chmod -R u+w runtime/evidence-cells && rm -rf -- runtime/evidence-cells; fi
    uv run python evidence/scripts/build-cells.py --private-key-root config/evidence/local/cells --output runtime/evidence-cells
    uv run python scripts/project-runtime-secrets.py
    uv run scripts/check-signer-public-keys.py

build-runtime-images:
    scripts/build-registry-stack-runtime.sh

# Compile production Relay packages and publish deterministic SQLite sources.
prepare-runtime: build-runtime-images
    uv run scripts/check-signer-public-keys.py
    scripts/prepare-authority-runtime.sh

prepare: generate prepare-runtime

metadata-publish:
    uv run scripts/publish-metadata.py

metadata-publish-check:
    uv run scripts/publish-metadata.py --check

lint:
    uvx ruff check --select E4,E7,E9,F --exclude vendor .
    scripts/check-fiction.sh
    scripts/check-config-secrets.py
    scripts/check-image-pins.py
    scripts/hosted-image-manifest.py inventory
    scripts/check-runtime-topology.py
    scripts/check-registry-stack-release-pin.py
    uv run scripts/check-signer-public-keys.py
    just metadata-publish-check
    uv run scripts/metadata-lint.py
    cd portal && pnpm check
    cd home && pnpm check

test:
    cd generator && uv run python -m unittest discover -s tests
    uv run python -m unittest discover -s scenario-runner -p 'test_*.py'
    uv run python -m unittest relays/test_relay_projects.py evidence/tests/test_cells.py scripts/test_metadata_authority_contracts.py scripts/test_image_pins.py scripts/test_build_registry_stack_runtime.py scripts/test_hosted_image_manifest.py scripts/test_hosted_provisioning_topology.py scripts/test_hosted_network_isolation.py scripts/test_hosted_home_topology.py scripts/test_hosted_esignet_topology.py scripts/test_hosted_evidence_routes.py scripts/test_hosted_runtime_assets.py scripts/test_provision_hosted_runtime.py scripts/test_hosted_transit_signer.py scripts/test_smoke_hosted_provisioner_image.py scripts/test_runtime_topology.py scripts/test_registry_stack_release_pin.py scripts/test_hosted_authority_rollout.py scripts/test_local_relay_runtime_stager.py scripts/test_local_transit_proxy.py scripts/test_local_transit_signers.py scripts/test_local_transit_providers.py scripts/test_signer_public_keys.py scripts/test_project_runtime_secrets.py scripts/test_gen_secrets.py scripts/test_publish_runtime_extracts.py scripts/test_lifecycle_proof.py scripts/test_live_lifecycle_proof.py scripts/test_local_relay_source_publisher.py scripts/test_smoke_programme_acceptance.py scripts/test_smoke_esignet.py
    cd portal && pnpm test
    cd home && pnpm test

# Validate local, hosted, eSignet, and every Coolify topology without starting it.
compose:
    @test -f .env || { echo ".env is missing; run just gen-secrets" >&2; exit 1; }
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml config >/dev/null
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.esignet.yaml config >/dev/null
    @scripts/check-hosted-compose.sh
    @scripts/check-coolify-compose.sh

# Verify that every Registry Stack v0.22.0 release reference is public and immutable.
hosted-pin-check: build-runtime-images
    scripts/check-image-pins.py
    scripts/check-registry-stack-release-pin.py --require-public

# Run all four relayctl production gates against the five authored projects.
relay-check: build-runtime-images
    scripts/check-relay-projects.sh

# Check the six running Evidence deployments and all eleven authored fixtures.
evidence-check:
    scripts/check-evidence-cells.sh

signers-up:
    uv run scripts/local-transit-signers.py up
    scripts/check-local-transit-providers.py

signers-down:
    uv run scripts/local-transit-signers.py down

up: prepare
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml up -d --build --force-recreate

up-esignet: prepare
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.esignet.yaml up -d --build --force-recreate

down:
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml down
    just signers-down

down-esignet:
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.esignet.yaml down
    just signers-down

# Destructive reset is intentionally local-only. Hosted rollout never deletes volumes.
reset:
    COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml down -v

rollout phase:
    scripts/hosted-authority-rollout.py {{ phase }}

smoke:
    scripts/smoke.sh

smoke-esignet:
    @uv run scripts/smoke-esignet.py >/dev/null && node scripts/smoke-esignet-login.mjs || { echo "smoke-esignet: FAIL"; exit 1; }

programme-acceptance:
    @COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml exec -T scenario-runner python - < scripts/smoke-programme-acceptance.py 2>/dev/null || { echo "programme-acceptance: FAIL scenario-runner-execution"; exit 1; }

lifecycle-proof:
    uv run scripts/live-lifecycle-proof.py

lifecycle-fixture-proof:
    uv run scripts/lifecycle_proof.py

portal-live-e2e:
    cd portal && SOLMARA_PORTAL_E2E_MODE=hosted PLAYWRIGHT_BASE_URL="http://127.0.0.1:${SOLMARA_PORTAL_PORT:-4300}" pnpm e2e

home-live-e2e:
    cd home && SOLMARA_HOME_E2E_MODE=live PLAYWRIGHT_BASE_URL="http://127.0.0.1:${SOLMARA_HOME_PORT:-4301}" pnpm e2e
