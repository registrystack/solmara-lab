# Solmara Lab Hosted Deployment

Status: operational runbook for the public Solmara Lab deployment.

This guide explains how to deploy Solmara Lab to Coolify from this repository.
It intentionally avoids private control-plane coordinates, credential file
paths, API tokens, and environment values. Keep those in the private operations
store for the environment you are deploying.

## Deployment Model

The hosted lab is split into one Coolify Docker Compose application for the
edge services, plus one Coolify application per pseudo-government authority.
The split keeps each authority's Redis, Postgres, relay cache, notary state, and
audit volumes under that authority's app instead of sharing one large Compose
project.

| Coolify app name | Compose file | Services |
|---|---|---|
| `solmara-lab` | `compose.coolify.yaml` | Visitor Center, portal, scenario runner, static metadata |
| `solmara-lab-interior` | `compose.coolify.interior.yaml` | CRA relay, NIA relay, NIA Postgres |
| `solmara-lab-esignet` | `compose.coolify.esignet.yaml` | eSignet, public eSignet edge proxy, eSignet UI, eSignet Postgres, Redis, seed jobs |
| `solmara-lab-social-development` | `compose.coolify.social-development.yaml` | SRO relay, programme MIS relay, child benefit notary, Redis |
| `solmara-lab-labour-pensions` | `compose.coolify.labour-pensions.yaml` | SIPF relay, pension notary, Redis |
| `solmara-lab-agriculture` | `compose.coolify.agriculture.yaml` | NAgDI relay, NAgDI notary, Redis |
| `solmara-lab-citizen-services` | `compose.coolify.citizen-services.yaml` | citizen services notary, citizen OID4VCI issuer notary, Redis |
| `solmara-lab-wallet` | `compose.coolify.walt.yaml` | Walt holder wallet API, Walt web wallet, Postgres, Caddy |

Hosted compose files follow these rules:

- No host ports. Coolify owns public routing.
- No repo bind mounts. Coolify does not seed bind-mount sources from the Git checkout.
- No custom Docker networks. Cross-app calls use public HTTPS endpoints.
- No `build:` blocks. Hosted services run digest-pinned images from GHCR.
- Relay audit/cache and Notary audit state use named volumes owned by the runtime UID.

## Public Endpoints

The current public hostname pattern is `*.solmara.registrystack.org`.

| Service | Domain |
|---|---|
| Visitor Center | `https://solmara.registrystack.org` |
| Portal | `https://portal.solmara.registrystack.org` |
| Static metadata | `https://metadata.solmara.registrystack.org` |
| eSignet | `https://esignet.solmara.registrystack.org` |
| eSignet UI | `https://esignet-ui.solmara.registrystack.org` |
| Walt holder wallet | `https://wallet.solmara.registrystack.org` |
| CRA civil relay | `https://cra-relay.solmara.registrystack.org` |
| NIA population relay | `https://nia-relay.solmara.registrystack.org` |
| SRO social relay | `https://sro-relay.solmara.registrystack.org` |
| Programme MIS relay | `https://mosd-programme-relay.solmara.registrystack.org` |
| SIPF pensions relay | `https://sipf-relay.solmara.registrystack.org` |
| NAgDI agriculture relay | `https://nagdi-relay.solmara.registrystack.org` |
| Child benefit notary | `https://child-benefit-notary.solmara.registrystack.org` |
| Pension notary | `https://pension-notary.solmara.registrystack.org` |
| NAgDI notary | `https://nagdi-notary.solmara.registrystack.org` |
| Citizen services notary | `https://citizen-notary.solmara.registrystack.org` |
| Citizen OID4VCI issuer notary | `https://citizen-issuer-notary.solmara.registrystack.org` |

## Image Model

Hosted deployment uses two layers of images.

Registry Stack product images are workflow inputs:

- `registry_relay_image`: digest-pinned `registry-relay` image.
- `registry_notary_image`: digest-pinned `registry-notary` image.

Solmara-owned wrapper and application images are built by the
`release-candidate` workflow and reported as digest-pinned refs:

- `SOLMARA_RELAY_IMAGE`
- `SOLMARA_NOTARY_IMAGE`
- `SOLMARA_POSTGRES_IMAGE`
- `SOLMARA_STATIC_METADATA_IMAGE`
- `SOLMARA_SCENARIO_RUNNER_IMAGE`
- `SOLMARA_HOME_IMAGE`
- `SOLMARA_PORTAL_IMAGE`
- `SOLMARA_ESIGNET_RELAY_IMAGE`
- `SOLMARA_ESIGNET_POSTGRES_IMAGE`
- `SOLMARA_ESIGNET_UI_IMAGE`
- `SOLMARA_ESIGNET_SEED_IMAGE`

The Walt holder wallet app uses upstream Walt, Postgres, Caddy, and Alpine
images pinned by explicit version tags in `compose.coolify.walt.yaml`; it does
not build Solmara-owned images.

The relay and notary wrapper images copy hosted configs into product images:

- `docker/relay/Dockerfile` copies `ministries/`, overlays
  `hosted/ministries/`, and adds the hosted Postgres CA certificate.
- `docker/notary/Dockerfile` copies `hosted/notaries/`.
- `docker/esignet-relay/Dockerfile` builds the Relay-backed eSignet
  authenticator plugin and adds it to the MOSIP eSignet base image.
- `docker/esignet-postgres/Dockerfile`, `docker/esignet-ui/Dockerfile`, and
  `docker/esignet-seed/Dockerfile` bake the Solmara eSignet init/config/seed
  assets needed by Coolify, without repo bind mounts.
- The hosted eSignet seed service writes `/tmp/ready` and idles after a
  successful seed so Coolify keeps the compose deployment healthy. The local
  eSignet seed still exits successfully so the local portal can depend on
  `service_completed_successfully`.

The Solmara image tag should normally be the commit SHA being deployed. Coolify
env vars must use immutable `image@sha256:<digest>` refs, not mutable tags.

## Hosted Config Overlays

Local configs use Compose-private service names. Hosted configs use public HTTPS
URLs because each authority is a separate Coolify application.

After changing any relay or notary config, regenerate the hosted overlays:

```bash
uv run scripts/render-hosted-configs.py
```

Check overlays before deployment:

```bash
uv run scripts/render-hosted-configs.py --check
```

The renderer also rejects plaintext hosted URLs and the private-network escape
flag in hosted notary source connections.

## Required Environment Variables

Create production env vars in each Coolify application. Preview env rows are not
used by the public deployment.

Image refs:

- Set every `SOLMARA_*_IMAGE` variable required by the app's compose file.
- Set `REGISTRY_STACK_PLATFORM=linux/amd64` unless the product release publishes
  a different platform.
- Optional: `VOLUME_INIT_IMAGE`, otherwise compose uses `busybox:1.36`.

Shared runtime settings:

- `RUST_LOG`
- `REGISTRY_RELAY_AUDIT_HASH_SECRET`
- `REGISTRY_NOTARY_AUDIT_HASH_SECRET`
- `REGISTRY_NOTARY_REPLAY_REDIS_URL`
- `REGISTRY_PLATFORM_REDIS_TEST_URL`
- `SOLMARA_POSTGRES_USER`
- `SOLMARA_POSTGRES_PASSWORD`
- `SOLMARA_POSTGRES_DB`
- `SOLMARA_NIA_DATABASE_URL`
- `SOLMARA_ESIGNET_POSTGRES_PASSWORD`
- `REGISTRY_ESIGNET_KYC_KEYSTORE_PASSWORD`
- `REGISTRY_ESIGNET_KYC_TOKEN_SECRET`
- `REGISTRY_ESIGNET_PSUT_SECRET`

Portal and Visitor Center:

- `REPO_URL`
- `UMAMI_WEBSITE_ID`
- `PORTAL_SESSION_SECRET`
- `PORTAL_AUTH_PROVIDER=esignet`
- `PORTAL_ESIGNET_CLIENT_ID`
- `PORTAL_ESIGNET_CLIENT_KEY_ID`
- `PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64`
- `PORTAL_ESIGNET_ISSUER`
- `PORTAL_ESIGNET_AUTHORIZATION_ENDPOINT`
- `PORTAL_ESIGNET_TOKEN_ENDPOINT`
- `PORTAL_ESIGNET_CLIENT_ASSERTION_AUDIENCE`
- `PORTAL_ESIGNET_USERINFO_ENDPOINT`
- `PORTAL_ESIGNET_REDIRECT_URI`
- `PORTAL_ESIGNET_SCOPE`
- `PORTAL_ESIGNET_SUBJECT_CLAIM`
- `PORTAL_RELAY_TOKEN`
- `CHILD_BENEFIT_NOTARY_TOKEN`
- `PENSION_NOTARY_TOKEN`
- `NAGDI_NOTARY_TOKEN`
- `PORTAL_CITIZEN_NOTARY_TOKEN`

Citizen OID4VCI issuer:

- `CITIZEN_ISSUER_NOTARY_ISSUER_JWK`
- `CITIZEN_ISSUER_NOTARY_ACCESS_TOKEN_JWK`
- `CITIZEN_ISSUER_ESIGNET_RP_JWK`
- `CITIZEN_ISSUER_ESIGNET_CLIENT_PRIVATE_KEY_B64`

The `CITIZEN_ISSUER_ESIGNET_RP_JWK` value and
`CITIZEN_ISSUER_ESIGNET_CLIENT_PRIVATE_KEY_B64` value must be derived from the
same RSA private key. eSignet stores the public key for client
`solmara-citizen-issuer`; the issuer notary uses the matching private JWK to
sign `private_key_jwt` assertions when it exchanges the citizen login code.

Walt holder wallet:

- `CONFIG_REPO_REF`
- `WALT_DB_PASSWORD`
- `WALT_AUTH_ENCRYPTION_KEY`
- `WALT_AUTH_SIGN_KEY`
- `WALT_AUTH_TOKEN_KEY`
- `WALT_KTOR_SIGNING_KEY`
- `WALT_KTOR_VERIFICATION_KEY`

Relay token hashes and notary source tokens:

- Use the variable names referenced by the relevant compose file.
- Store raw API tokens only as environment variables.
- Committed configs must keep using `token_env`, `private_jwk_env`,
  `hash_secret_env`, and fingerprint references.

eSignet uses the NIA population registry only through the
`solmara-nia-userinfo` attribute-release profile:

- Set `SOLMARA_ESIGNET_IDENTITY_RELEASE_HASH` on `solmara-lab-interior`.
- Set the matching `SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW` on
  `solmara-lab-esignet`.
- Do not grant eSignet `nia_population:rows`; the release key needs only
  `nia_population:metadata` and `nia_population:identity_release`.

Do not print full env dumps while deploying. Coolify API responses can include
real env values when the token has sensitive read access.

## Coolify App Setup

For each app:

1. Create or reuse a Coolify application.
2. Set the Git repository to this repo and branch to `main`.
3. Set the build pack to Docker Compose.
4. Set the compose location to the app's `compose.coolify*.yaml` file.
5. Disable auto-generated domains.
6. Avoid connecting apps through a shared custom Docker network.
7. Add only the production environment variables needed by that compose file.
8. Attach domains to the compose service names listed below.

When using the Coolify API for `docker_compose_domains`, use the exact
hyphenated service names from the compose file, not the underscore-normalized
names that Coolify stores internally.

| Compose service | Domain |
|---|---|
| `home` | `https://solmara.registrystack.org:4301` |
| `portal` | `https://portal.solmara.registrystack.org:4000` |
| `static-metadata` | `https://metadata.solmara.registrystack.org:8080` |
| `esignet-edge` | `https://esignet.solmara.registrystack.org:3000` |
| `esignet-ui` | `https://esignet-ui.solmara.registrystack.org:3000` |
| `caddy` | `https://wallet.solmara.registrystack.org:7101` |
| `cra-civil-relay` | `https://cra-relay.solmara.registrystack.org:8080` |
| `nia-population-relay` | `https://nia-relay.solmara.registrystack.org:8080` |
| `sro-social-relay` | `https://sro-relay.solmara.registrystack.org:8080` |
| `programme-mis-relay` | `https://mosd-programme-relay.solmara.registrystack.org:8080` |
| `sipf-pensions-relay` | `https://sipf-relay.solmara.registrystack.org:8080` |
| `nagdi-agriculture-relay` | `https://nagdi-relay.solmara.registrystack.org:8080` |
| `child-benefit-notary` | `https://child-benefit-notary.solmara.registrystack.org:8080` |
| `pension-notary` | `https://pension-notary.solmara.registrystack.org:8080` |
| `nagdi-notary` | `https://nagdi-notary.solmara.registrystack.org:8080` |
| `citizen-notary` | `https://citizen-notary.solmara.registrystack.org:8080` |
| `citizen-issuer-notary` | `https://citizen-issuer-notary.solmara.registrystack.org:8080` |

## Release And Deploy

1. Confirm the Registry Stack release image digests to deploy.

   ```bash
   just release-pins v0.8.4
   ```

2. Run the release-candidate workflow from GitHub Actions.

   Inputs:

   - `registry_relay_image`
   - `registry_notary_image`
   - `solmara_image_tag`

   The workflow runs generation, lint, tests, compose validation, local smoke,
   portal e2e, Visitor Center e2e, and then builds and pushes Solmara images.

3. Copy the reported Solmara image digests into Coolify production env
   vars for the relevant apps.

4. Validate the local tree before redeploying:

   ```bash
   just lint
   just test
   just compose
   ```

5. Deploy in dependency order:

   ```text
   solmara-lab-interior
   solmara-lab-esignet
   solmara-lab-social-development
   solmara-lab-labour-pensions
   solmara-lab-agriculture
   solmara-lab-citizen-services
   solmara-lab-wallet
   solmara-lab
   ```

The core app should deploy last because its Visitor Center and portal call the
public relay, notary, and eSignet endpoints.

## Verification

Run the hosted smoke from a trusted shell with the demo tokens available in
`.env` or the process environment:

```bash
just hosted-smoke
```

The command runs:

- Public route and `/healthz` checks for the Visitor Center, portal, metadata,
  Walt wallet, six relays, and five notaries.
- OID4VCI issuer checks for issuer metadata, VCT metadata, credential offer,
  nonce issuance, refusal of unknown credential configurations, eSignet login
  redirect, and unauthenticated credential refusal.
- eSignet discovery checks for issuer-root OpenID and OAuth metadata, plus the
  MOSIP `/v1/esignet/...` discovery path.
- A Visitor Center scenario-proxy check that lists the stories, runs the child
  benefit positive path, confirms credential issuance, and runs the purpose
  denial path.
- Authenticated Relay source probes.
- Authenticated Notary scenario checks.
- Published demo-token refusal checks.
- Portal live BFF login and evaluation smoke.

Expected success:

```text
smoke-hosted: Solmara hosted smoke passed
```

Then verify eSignet and the NIA identity-release backend:

```bash
just smoke-esignet -- \
  --relay-url https://nia-relay.solmara.registrystack.org \
  --esignet-url https://esignet.solmara.registrystack.org \
  --esignet-ui-url https://esignet-ui.solmara.registrystack.org
```

The eSignet smoke loads `SOLMARA_ESIGNET_IDENTITY_RELEASE_RAW` from `.env` or
the process environment, checks discovery, reads Elena's fixture `legacy_nid`,
and verifies that NIA resolves it to Solmara UIN `2300018263`.

For the browser pass, run:

```bash
SOLMARA_HOSTED_SMOKE_BROWSER=1 just hosted-smoke
```

Browser mode reuses the public hosted URLs and does not start local SvelteKit
servers.

The authenticated parts are important. `/healthz` can pass while evaluation
requests fail because audit writes, replay storage, source authorization, or
credential issuance is misconfigured.

## Audit And State Volumes

Registry Relay and Registry Notary write audit records under fail-closed policy.
Do not bypass that policy for hosted deployment. If an audit sink cannot write,
the correct behavior is a stable `audit.write_failed` problem response.

Hosted authority compose files must keep:

- Relay cache volumes mounted at `/var/lib/registry-relay/cache`.
- Relay audit volumes mounted at `/var/lib/registry-relay/audit`.
- Notary state volumes mounted at `/var/lib/registry-notary/config-state`.
- A `volume-permissions` service that chowns relay volumes to UID `65532` and
  notary volumes to UID `65534`.
- `depends_on: volume-permissions: condition: service_healthy` on services that
  write those volumes.

The `volume-permissions` service intentionally stays running after chowning.
Coolify injects restart behavior into compose services, so a short-lived
completed init container can block deployment. The sidecar writes `/tmp/ready`
and idles so Docker Compose can gate dependent services on a health check.

## Common Failure Modes

### `audit.write_failed`

Symptom: public `/healthz` succeeds, but `/v1/claims` or `/v1/evaluations`
returns `500` with `code: audit.write_failed`.

Checks:

1. Confirm the notary service mounts a named volume at
   `/var/lib/registry-notary/config-state`.
2. Confirm relay services mount named volumes at `/var/lib/registry-relay/audit`
   and `/var/lib/registry-relay/cache`.
3. Confirm `volume-permissions` is present, healthy, and mounts the same named
   volumes.
4. Redeploy the affected authority app after fixing compose.
5. Run `just hosted-smoke`.

Do not change audit write policy to make the error disappear.

### Domain patch accepted but no public route

Coolify stores compose service domain keys with underscores, but the domain API
input must use the compose service names. If a patch uses
`child_benefit_notary` instead of `child-benefit-notary`, Coolify may accept the
request without creating the intended service router. Patch domains with the
hyphenated service names and redeploy.

### Hosted config still calls Compose DNS

If a notary tries to call `http://cra-civil-relay:8080` in hosted deployment,
the hosted overlay is stale. Regenerate and commit `hosted/` configs:

```bash
uv run scripts/render-hosted-configs.py
uv run scripts/render-hosted-configs.py --check
```

### Old image parses config incorrectly

If containers fail on unknown config fields, the hosted config and product image
digests are out of step. Deploy a compatible Registry Stack release image pair,
rebuild Solmara wrapper images with those inputs, and update Coolify image env
vars to the new digests.

## Privacy And Change Control

- Do not commit `.env`, raw tokens, private keys, API tokens, Coolify API token
  paths, or full environment dumps.
- Do not copy private operations notes into this repo.
- Prefer recording public, reproducible facts here: compose files, domain
  service names, image env var names, verification commands, and failure modes.
- Keep private evidence, deployment UUIDs, host coordinates, and secret handling
  notes in the private operations repo.
