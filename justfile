set dotenv-load
set positional-arguments

compose_project_name := `python3 scripts/compose_project_name.py`

default:
    @just --list

# Install local development dependencies when subprojects define them.
setup:
    @if [ -f pyproject.toml ]; then uv sync; fi
    @if [ -f generator/pyproject.toml ]; then cd generator && uv sync; fi
    @if [ -f portal/package.json ]; then cd portal && pnpm install --frozen-lockfile; fi
    @if [ -f home/package.json ]; then cd home && pnpm install --frozen-lockfile; fi

# Generate deterministic fixtures and local secrets.
generate:
    @if [ -f generator/pyproject.toml ]; then cd generator && uv run python -m solmara_lab.generate; else echo "generator/pyproject.toml missing"; exit 1; fi
    scripts/gen-secrets.py

# Generate a clean checkout, verify compiler output, and start the local topology.
up-generated:
    just generate
    just registry-projects-runtime-check
    just up

# Validate every authority-owned Registry project in both deployment profiles.
registry-projects-check:
    scripts/registry-projects.sh check

# Print the complete redacted acquisition and disclosure plan for every authority.
registry-projects-review:
    scripts/registry-projects.sh review

# Inspect compiled, declared, enabled, used, and missing capabilities.
registry-projects-capabilities:
    scripts/registry-projects.sh capabilities

# Install or refresh version-matched VS Code and Zed schema mappings.
registry-projects-editor:
    scripts/registry-projects.sh editor

# Run every synthetic authority integration fixture offline.
registry-projects-test:
    scripts/registry-projects.sh test

# Build the Registry compiler outputs for every authority project.
registry-projects-build environment="local":
    scripts/registry-projects.sh build {{ environment }}

# Refresh the committed runtime closure from all authored authority projects.
registry-projects-sync:
    scripts/registry-projects.sh sync-runtime

# Prove the committed runtime closure matches the authored authority projects.
registry-projects-runtime-check:
    scripts/registry-projects.sh check-runtime

# Generate only local secrets.
gen-secrets:
    scripts/gen-secrets.py

# Check the paired Mint config and all authored Registry Evidence fixtures.
evidence-check:
    scripts/check-evidence-runtime.py

# Prove the released v0.18.0 SQLite-extract starter in a fresh directory.
evidence-sqlite-extract-demo:
    scripts/demo-evidence-sqlite-extract.py

# Publish the static metadata bundle served by static-metadata.
metadata-publish:
    @if command -v registry-manifest-cli >/dev/null 2>&1; then registry-manifest-cli publish metadata/solmara-wave1.metadata.yaml --out metadata/public/metadata --site-root metadata/public; fi
    uv run scripts/publish-metadata.py

# Check that the committed static metadata bundle is up to date.
metadata-publish-check:
    uv run scripts/publish-metadata.py --check

# Lint the published metadata bundle.
metadata-lint:
    uv run scripts/metadata-lint.py

# Static repository checks.
lint:
    scripts/check-fiction.sh
    scripts/check-image-pins.py
    scripts/check-config-secrets.py
    just metadata-publish-check
    just metadata-lint
    @if [ -f portal/package.json ]; then cd portal && pnpm check; fi
    @if [ -f home/package.json ]; then cd home && pnpm check; fi

# Unit and integration tests that can run without a full Compose stack.
test:
    @if [ -f generator/pyproject.toml ]; then cd generator && uv run python -m unittest discover -s tests; fi
    uv run python3 -m unittest discover -s scenario-runner -p 'test_*.py'
    @if [ -f portal/package.json ]; then cd portal && pnpm test; fi
    @if [ -f home/package.json ]; then cd home && pnpm test; fi
    uv run python3 -m unittest scripts/test_demo_evidence_sqlite_extract.py scripts/test_gen_secrets.py scripts/test_image_pins.py scripts/test_migrate_local_audit.py scripts/test_quality_scripts.py scripts/test_registry_stack_runtime.py scripts/test_registry_stack_tool.py scripts/test_registryctl_build_output.py scripts/test_registryctl_test_output.py scripts/test_release_pins.py scripts/test_relay_workload_identity_agent.py scripts/test_smoke_esignet.py scripts/test_smoke_hosted.py scripts/test_smoke_nia_attribute_release.py scripts/test_smoke_portal_compose.py scripts/test_smoke_relay_sources.py

# Validate Compose files without starting services.
compose:
    @if [ ! -f .env ]; then echo ".env is missing; run 'just gen-secrets' first" >&2; exit 1; fi
    @if [ -f compose.yaml ]; then COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml config >/dev/null; fi
    @if [ -f compose.esignet.yaml ]; then COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.esignet.yaml config >/dev/null; fi

# Start the local topology.
up:
    scripts/build-registry-stack-runtime.sh
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml up -d --build

# Compatibility alias: all local starts now build Relay, Evidence, and Mint from source.
up-dev:
    just up

# Stop the local topology without removing local volumes.
down:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml down

# Start the local topology with eSignet-backed portal login.
up-esignet:
    scripts/build-registry-stack-runtime.sh
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml up -d --build

# Compatibility alias for the source-built eSignet topology.
up-esignet-dev:
    just up-esignet

# Stop the local eSignet topology without removing local volumes.
down-esignet:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml down

# Stop the local topology and remove this checkout's local volumes.
reset:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml down -v

# Stop the local eSignet topology and remove this checkout's local eSignet volumes.
reset-esignet:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{ compose_project_name }}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml down -v

# Run story and authority-application smokes against the running local topology.
smoke:
    scripts/smoke.sh

# Run only live HTTP checks against the running local topology.
smoke-live:
    uv run --locked scripts/smoke-live.py

# Smoke eSignet discovery; portal login proves the NIA attribute-release path end to end.
smoke-esignet *args:
    uv run scripts/smoke-esignet.py {{ args }}

# Probe the Relay Records APIs used by Registry Evidence.
relay-source-smoke:
    scripts/smoke-relay-sources.py

# Smoke the Compose portal service and live BFF wiring.
portal-compose-smoke:
    scripts/smoke-portal-compose.py

# Run browser e2e against the live local topology.
portal-live-e2e:
    @cd portal && SOLMARA_PORTAL_E2E_MODE=hosted PLAYWRIGHT_BASE_URL="http://127.0.0.1:${SOLMARA_PORTAL_PORT:-4300}" pnpm e2e

# Run browser e2e against the Visitor's Center.
home-live-e2e:
    @cd home && SOLMARA_HOME_E2E_MODE=live PLAYWRIGHT_BASE_URL="http://127.0.0.1:${SOLMARA_HOME_PORT:-4301}" pnpm e2e

# Run release-readiness and security-oriented checks.
review:
    scripts/review.sh
