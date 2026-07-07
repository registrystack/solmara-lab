# Solmara Lab

Solmara Lab is a standalone Registry Stack adopter demo for the fictional
Republic of Solmara. It replaces the old monorepo lab with one coherent country
story, generated synthetic data, purpose-limited Relay APIs, Notary evidence
services, and a citizen portal wired to the real local stack.

The lab uses published Registry Stack images pinned by digest. A local
`registry-stack` checkout is useful for development, but it is not required for
normal generation, live smoke tests, portal e2e, or hosted deployment.

## Quick Start

From this repository:

```bash
just setup
just generate
just up
just smoke
just portal-live-e2e
just down
```

`just up`, `just down`, and `just reset` use a checkout-specific Docker Compose
project name by default so two local clones do not share containers or volumes.
Use `just down` to stop services while keeping local data. Use `just reset` only
when you intend to delete this checkout's Compose volumes.

The first wave covers three journeys:

- Birth to child benefit.
- Death to pension stop plus survivor benefit.
- Farmer climate-smart voucher and livestock movement control.

## Repository Map

- `docs/` contains the Solmara world bible, purpose catalogue, naming record,
  and story docs.
- `generator/` owns deterministic truth tables, per-registry projections, and
  generated fixture checks.
- `geo/` contains the hand-authored Solmara geometry source used by the
  generator.
- `ministries/` contains authority-owned Relay configs, manifest fragments,
  crosswalks, and generated fixtures.
- `notaries/` contains purpose-oriented Notary configs.
- `metadata/` assembles the multi-authority metadata publication.
- `portal/` contains the citizen portal and BFF.
- `scenarios/`, `requests/`, and `perf/` carry guided scenarios, API examples,
  and k6 smoke coverage.
- `scripts/` contains root quality gates and orchestration helpers.

## Development Commands

```bash
just lint       # static repo checks, including fiction lint
just test       # generator, portal, and script tests when their projects exist
just compose    # docker compose config validation
just smoke      # story previews plus live Relay, Notary, and Compose portal checks
just smoke-live # live Notary checks only
just portal-compose-smoke # HTTP smoke against the Compose portal and live BFF
just portal-live-e2e # browser e2e against the running local stack
just down       # stop the local Compose topology without deleting volumes
just reset      # stop the local Compose topology and delete its volumes
just release-pins v0.8.4 # compare versions.env against published GHCR tags
just review     # security and release-readiness checks
```

`just generate` rewrites generated fixtures. Review those diffs like any other
committed generated artifact.

## Image Pins

`versions.env` is the root source for published image digests. The Compose
fallbacks mirror it so direct `docker compose` runs still use pinned Registry
Stack images. The current pins are the Registry Stack `v0.8.4` release digest
assets. Because that release publishes amd64 images, Compose defaults
`REGISTRY_STACK_PLATFORM` to `linux/amd64`; override it only when the release
publishes an image for another platform.

The NIA population Relay is intentionally Postgres-backed. `just gen-secrets`
also creates local Postgres TLS material under `config/postgres/ssl/`, and the
generated NIA connection string includes `sslmode=require`, matching Registry
Stack `v0.8.4` Relay requirements.

## Privacy Rules

Solmara data is synthetic. Do not use real people, real email domains, real
addresses, or real administrative geography. Use `@mail.solmara.example` for
emails and keep all story domains under `gov.solmara.example`.
