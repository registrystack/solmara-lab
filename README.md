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
just up-generated
just smoke
just portal-live-e2e
just down
```

`just up`, `just down`, and `just reset` use a checkout-specific Docker Compose
project name by default so two local clones do not share containers or volumes.
Use `just down` to stop services while keeping local data. Use `just reset` only
when you intend to delete this checkout's Compose volumes.

`up-generated` is the single clean-checkout generate/start journey. It creates
the synthetic fixtures and local secrets, regenerates every authority's Relay
and Notary closure with the real `registryctl` version pinned in `versions.env`,
compares those closures with the committed runtime, and starts the topology.
If the exact tool version is not installed, the helper downloads the matching
release binary and verifies it against the release SHA-256 file.

`registry-projects-runtime-check` can run the compiler comparison without
starting services. The project wrapper consumes Registryctl's versioned JSON
build report and validates its project-owned output root rather than depending
on Registryctl's private build-directory layout. Its fixture gate also
consumes the versioned test report and requires independently authored
request-to-consultation evidence for every reachable target. Integration-only
fixtures are not accepted as caller compatibility proof.
`contract-generation-proof` is a separate release gate for one bounded SRO
authority pair. It compiles a harmless successor, proves the blue pair works,
rejects a mixed Relay/Notary generation before Relay execution or source
dispatch, activates the complete successor, and proves it works. Its temporary
Compose project and volumes are removed when the check finishes.

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
- `demos/opencrvs-v2/` contains an optional, isolated OpenCRVS interoperability
  demo. Its released live path is blocked; paired candidate use is
  development-only. It is not part of the six-authority topology.
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
just up # local stack with mock portal login
just up-esignet # local stack with eSignet-backed portal login
just up-dev # explicit source-built Relay development stack
just up-esignet-dev # source-built Relay development stack with eSignet
just smoke-esignet # eSignet public discovery smoke
just down       # stop the local Compose topology without deleting volumes
just reset      # stop the local Compose topology and delete its volumes
just up-generated # clean-checkout generation, compiler comparison, and start
just registry-projects-runtime-check # regenerate and compare all authority runtime closures
just hosted-relay-bundles-check # verify hosted Relay signatures and config closure
just registry-projects-review # complete redacted acquisition and disclosure reports
just registry-projects-capabilities # value-free installed/used/missing capability inventory
just registry-projects-editor # version-matched VS Code and Zed schemas for all projects
just contract-generation-proof # release-only live SRO blue/mixed/successor proof
just opencrvs-demo-test # optional OpenCRVS fixture and compiler proof
just opencrvs-demo-candidate-build <worktree> # build matched pre-release compiler and Relay
just opencrvs-demo-compose # validate the isolated demo topology
just opencrvs-demo-up # start with compatible release or paired dev artifacts
just opencrvs-demo-proof # live proof with compatible release or paired dev artifacts
just opencrvs-demo-down # remove its containers, volumes, and runtime closure
just release-pins <registry-stack-tag> # compare committed versions.env pins against a candidate or release tag
just review     # normal security and release-readiness checks
just review-release <registry-stack-tag> # candidate review with published pin validation
```

The OpenCRVS demo's offline compiler, fixture, Compose, and paired pre-release
live checks pass. Its released live path remains blocked. Relay v0.15.2 has the
strict no-expiry OAuth decoder, yet its durable state plane rejects this
no-cache script plan before source dispatch. Registryctl v0.15.2 also cannot
author the profile. One exact pending Registry Stack commit enables offline
compiler development only. Pre-release live development requires Registryctl
and a labeled Relay image built from one later exact candidate commit
containing the authoring, state-plane, and active script-budget fixes. Do not
deploy the demo until a Registry Stack release contains those fixes and all
coordinated pins in `versions.env` have passed release review. The safe paired
override, exact native endpoints, cleanup sequence, privacy boundary, and
direct machine issuance limits are documented in
[`demos/opencrvs-v2/README.md`](demos/opencrvs-v2/README.md).

Normal startup pulls the immutable canonical Relay image pinned in
`versions.env`; it does not clone or compile Registry Stack. Governed attribute
release is part of the canonical Registry Stack v0.15.2 Relay build. The
`*-dev` recipes are the explicit source-build path. They verify the pinned
source commit and build the same default feature set into a separate local
image, leaving the standalone path unchanged.

`just generate` rewrites generated fixtures. Review those diffs like any other
committed generated artifact.

Each authority project commits Registryctl-generated schemas plus VS Code and
Zed mappings under its own project directory. Open that authority directory as
the editor workspace to get validation and completion for its project,
environment, integration, fixture, and entity YAML. Refresh all six with
`just registry-projects-editor` only after updating the pinned Registryctl
release. CI reruns the generator and fails on drift, so the editor contract
cannot silently move to a different Registry Stack version.

## Image Pins

`versions.env` is the root source for the published Registry Stack image
digests and the exact source ref and commit used for release binding and the
explicit Relay development build. The Registry Stack `v0.15.2` Relay and
Notary images are both consumed directly by digest. Solmara does not publish
or select a feature-specific Relay runtime.

Use `just up` rather than invoking `docker compose up` directly so the
checkout-specific Compose project name and complete env-file set are applied.
Because the release publishes amd64 images, Compose defaults
`REGISTRY_STACK_PLATFORM` to `linux/amd64`; override it only when every
selected base image is available for another platform.

Every authority exposes one public Relay and one Notary. A separate private
consultation Relay shares only the Notary network namespace and is never
published on the Relay endpoint. Relay consultation state and all Notary
correctness state are PostgreSQL-backed. `just gen-secrets` creates local
PostgreSQL TLS material and distinct runtime and migrator passwords for each
authority. See
[`docs/notary-postgresql-state.md`](docs/notary-postgresql-state.md) for the
database map, diagnosis, backup, recovery, and upgrade workflow.

Local public and consultation Relay namespaces each have their own
loopback-only workload issuer. The consultation issuer writes the Notary token
to a private, authority-specific volume; duplicating the issuer process avoids
opening either Relay's loopback JWKS listener onto the shared Compose network.

The `REGISTRY_RELAY_STATE_EPOCH=v015` pin starts a fresh Relay state plane for
the v0.15.2 cache-persistence cutover. Earlier hosted deployments persisted
PostgreSQL publication pointers but not the immutable snapshot files they
referenced, so they cannot safely reuse the `v013` databases after adopting
durable Relay cache volumes. Keep the old `v013` databases quiesced for
rollback. The PostgreSQL runbook describes the stopped-writer and rollback
boundary.

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
authority-owned PostgreSQL state, separate public and consultation Relay
caches, and workload credentials. Notary containers do not use Redis or a
writable state directory.

Each hosted public Relay and private consultation Relay starts from its own
instance-bound signed Config Bundle and anti-rollback state. Only the
consultation bundle contains the private consultation artifacts. The wrapper
contains public trust anchors and signed closures only; the offline signing key
is not committed. A sequence-zero baseline is copied only when the matching
Relay state volume is empty, allowing first boot while keeping later bundle
sequence rollback protection durable in that volume.

Hosted workload agents keep Relay bearer credentials short-lived and confined
to per-consumer volumes. The separately served workload JWKS contains public
keys only; private workload JWKs remain Coolify secrets.

Run `just registry-projects-sync` after editing an authority project, then
`just registry-projects-runtime-check` to verify the local and hosted Relay and
Notary closures are deterministic.

Run `just hosted-smoke` after each hosted deploy from a trusted shell with the
demo tokens available in `.env` or the process environment. It checks public
routes, Relay source endpoints, Notary scenario evaluations, published-token
refusals, the Visitor Center scenario proxy, and the portal live BFF. Add
`SOLMARA_HOSTED_SMOKE_BROWSER=1` when you also want hosted Playwright coverage
for the Visitor Center and portal.

The `release-candidate` workflow verifies the pinned Registry Stack source and
uses the canonical published Relay digest as the base for the hosted Relay
wrapper. A Solmara candidate does not recompile Registry Stack. The workflow
builds the Solmara-owned images and writes their digest refs to the workflow
summary for Coolify env vars:
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
sign in through the portal with Elena's fixture UIN `2300018263` and static
OTP `111111`. This sign-in is the end-to-end check of the NIA
`solmara-nia-userinfo` attribute-release profile and its rotating eSignet
workload identity. Run `just smoke-esignet` for the public discovery checks.

Set `UMAMI_WEBSITE_ID` in the hosted environment to enable analytics for the
Visitor Center through the Registry Stack Umami instance.

## Privacy Rules

Solmara data is synthetic. Do not use real people, real email domains, real
addresses, or real administrative geography. Use `@mail.solmara.example` for
emails and keep all story domains under `gov.solmara.example`.
