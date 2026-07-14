set dotenv-load := true
set positional-arguments := true

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

# Validate every authority-owned Registry project in both deployment profiles.
registry-projects-check:
    scripts/registry-projects.sh check

# Run every synthetic authority integration fixture offline.
registry-projects-test:
    scripts/registry-projects.sh test

# Build private Relay and Notary inputs for every authority-owned project.
registry-projects-build environment="local":
    scripts/registry-projects.sh build {{environment}}

# Refresh the committed runtime closure from all authored authority projects.
registry-projects-sync:
    scripts/registry-projects.sh sync-runtime

# Prove the committed runtime closure matches the authored authority projects.
registry-projects-runtime-check:
    scripts/registry-projects.sh check-runtime

# Generate only local secrets.
gen-secrets:
    scripts/gen-secrets.py

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
    uv run python3 -m unittest discover -s scripts -p 'test_*.py'

# Validate Compose files without starting services.
compose:
    @if [ ! -f .env ]; then echo ".env is missing; run 'just gen-secrets' first" >&2; exit 1; fi
    @if [ -f compose.yaml ]; then COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose --env-file versions.env --env-file .env -f compose.yaml config >/dev/null; fi
    @if [ -f compose.hosted.yaml ]; then COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.hosted.yaml config >/dev/null; fi
    @if [ -f compose.esignet.yaml ]; then COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose --env-file versions.env --env-file .env -f compose.yaml -f compose.esignet.yaml config >/dev/null; fi
    scripts/check-coolify-compose.sh

# Start the local topology.
up:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml up -d --build

# Stop the local topology without removing local volumes.
down:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml down

# Start the local topology with eSignet-backed portal login.
up-esignet:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml up -d --build

# Stop the local eSignet topology without removing local volumes.
down-esignet:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml down

# Stop the local topology and remove this checkout's local volumes.
reset:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml down -v

# Stop the local eSignet topology and remove this checkout's local eSignet volumes.
reset-esignet:
    @env_args="--env-file versions.env"; if [ -f .env ]; then env_args="$env_args --env-file .env"; fi; COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-{{compose_project_name}}}" docker compose $env_args -f compose.yaml -f compose.esignet.yaml down -v

# Run story and authority-application smokes against the running local topology.
smoke:
    scripts/smoke.sh

# Run only live HTTP checks against the running local topology.
smoke-live:
    uv run --locked scripts/smoke-live.py

# Smoke eSignet discovery; portal login proves the NIA attribute-release path end to end.
smoke-esignet *args:
    uv run scripts/smoke-esignet.py {{args}}

# Probe Relay source endpoints used by live Notary smoke.
relay-source-smoke:
    scripts/smoke-relay-sources.py

# Smoke the Compose portal service and live BFF wiring.
portal-compose-smoke:
    scripts/smoke-portal-compose.py

# Run browser e2e against the live local topology.
portal-live-e2e:
    @cd portal && PORT="${PORT:-4001}" PORTAL_PROVIDER=live pnpm e2e

# Run browser e2e against the Visitor's Center.
home-live-e2e:
    @cd home && SOLMARA_HOME_E2E_MODE=live PLAYWRIGHT_BASE_URL="http://127.0.0.1:${SOLMARA_HOME_PORT:-4301}" pnpm e2e

# Run public hosted health, endpoint, scenario, and portal smoke checks.
hosted-smoke *args:
    uv run scripts/smoke-hosted.py {{args}}

# Verify pinned Registry Stack images match a published release tag.
release-pins tag="v0.8.4":
    scripts/check-release-pins.py {{tag}}

# Run release-readiness and security-oriented checks.
review:
    scripts/review.sh
