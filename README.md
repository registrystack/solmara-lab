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
- `ministries/` contains authority-owned source fixtures, manifest fragments,
  and crosswalks.
- `projects/` contains the six authority-owned Registry project sources. Each
  project generates one Relay config and one Notary config under `runtime/`.
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
just hosted-smoke # public hosted health, endpoint, scenario, and portal checks
just up-esignet # local stack with eSignet-backed portal login
just smoke-esignet # eSignet public discovery smoke
just down       # stop the local Compose topology without deleting volumes
just reset      # stop the local Compose topology and delete its volumes
just release-pins <registry-stack-tag> # compare committed versions.env pins against a candidate or release tag
just review     # normal security and release-readiness checks
just review-release <registry-stack-tag> # candidate review with published pin validation
```

`just generate` rewrites generated fixtures. Review those diffs like any other
committed generated artifact.

## Image Pins

`versions.env` is the root source for published image digests. The Compose
fallbacks mirror it so direct `docker compose` runs still use pinned Registry
Stack images. The current pins are the Registry Stack `v0.10.0` release digest
assets. Because that release publishes amd64 images, Compose defaults
`REGISTRY_STACK_PLATFORM` to `linux/amd64`; override it only when the release
publishes an image for another platform.

Every authority runs one Relay and one Notary. Relay consultation state and all
Notary correctness state are PostgreSQL-backed. `just gen-secrets` creates
local PostgreSQL TLS material and distinct runtime and migrator passwords for
each authority. See
[`docs/notary-postgresql-state.md`](docs/notary-postgresql-state.md) for the
database map, diagnosis, backup, recovery, and upgrade workflow.

## Hosted Deployment

See [`docs/hosted-deployment.md`](docs/hosted-deployment.md) for the full
runbook. Coolify uses one hosted Compose file for the lab edge plus four
ministry-grouped authority applications:

- `compose.coolify.yaml` for the Visitor Center, portal, scenario runner,
  child-benefit evidence composition, and static metadata.
- `compose.coolify.interior.yaml` for the CRA and NIA Relay and Notary pairs
  and their PostgreSQL databases.
- `compose.coolify.esignet.yaml` for eSignet, eSignet UI, and its backing
  Postgres/Redis/seed services.
- `compose.coolify.social-development.yaml` for the SRO and Programme Relay
  and Notary pairs and their PostgreSQL databases.
- `compose.coolify.labour-pensions.yaml` for the SIPF Relay and Notary pair and
  its PostgreSQL databases.
- `compose.coolify.agriculture.yaml` for the NAgDI Relay and Notary pair and
  its PostgreSQL databases.

The hosted compose files remove host port bindings and avoid repo bind mounts
because Coolify does not seed bind-mount sources from the Git checkout. They do
not define custom Docker networks; cross-authority calls use the public
`*.solmara.registrystack.org` TLS endpoints. Authority compose files preserve
authority-owned PostgreSQL state, persistent Relay snapshot caches, and
workload credentials. Notary containers do not use Redis or a writable state
directory.

Run `just registry-projects-sync` after editing an authority project, then
`just registry-projects-runtime-check` to verify the local and hosted Relay and
Notary closures are deterministic.

Run `just hosted-smoke` after each hosted deploy from a trusted shell with the
demo tokens available in `.env` or the process environment. It checks public
routes, Relay source endpoints, Notary scenario evaluations, published-token
refusals, the Visitor Center scenario proxy, and the portal live BFF. Add
`SOLMARA_HOSTED_SMOKE_BROWSER=1` when you also want hosted Playwright coverage
for the Visitor Center and portal.

The `release-candidate` workflow builds digest-pinned Solmara-owned images for
the hosted wrappers and app services, then writes the digest refs to the
workflow summary for Coolify env vars:
`SOLMARA_RELAY_IMAGE`, `SOLMARA_NOTARY_IMAGE`, `SOLMARA_POSTGRES_IMAGE`,
`SOLMARA_STATIC_METADATA_IMAGE`, `SOLMARA_HOME_IMAGE`,
`SOLMARA_PORTAL_IMAGE`, `SOLMARA_SCENARIO_RUNNER_IMAGE`,
`SOLMARA_ESIGNET_RELAY_IMAGE`, `SOLMARA_ESIGNET_POSTGRES_IMAGE`,
`SOLMARA_ESIGNET_UI_IMAGE`, and `SOLMARA_ESIGNET_SEED_IMAGE`.

Its manually supplied Registry Stack tag is required and must resolve to the
same Relay and Notary digests committed in `versions.env`. Run the same
candidate-only gate locally with `just review-release <registry-stack-tag>`;
the normal contributor and CI gate remains `just review`.

For local eSignet testing, run `just up-esignet` instead of `just up`, then
sign in through the portal with Elena's fixture `legacy_nid` and static OTP
`111111`. This sign-in is the end-to-end check of the NIA
`solmara-nia-userinfo` attribute-release profile and its rotating eSignet
workload identity. Run `just smoke-esignet` for the public discovery checks.

Set `UMAMI_WEBSITE_ID` in the hosted environment to enable analytics for the
Visitor Center through the Registry Stack Umami instance.

## Privacy Rules

Solmara data is synthetic. Do not use real people, real email domains, real
addresses, or real administrative geography. Use `@mail.solmara.example` for
emails and keep all story domains under `gov.solmara.example`.
