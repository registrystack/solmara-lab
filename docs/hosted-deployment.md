# Solmara Lab hosted deployment

Status: operational runbook for the public Solmara Lab deployment.

This guide describes the public Coolify topology without publishing private
control-plane coordinates or secret values. Keep those values in the private
operations store for the target environment.

## Deployment model

The hosted lab has one edge application and four authority applications. Each
authority runs one public Relay, one private consultation Relay, and one
Notary. Only the consultation Relay and Notary share a network namespace. The
public Relay remains independently routable, while the consultation Relay
binds only to loopback and is not published. Their PostgreSQL
correctness-state databases and roles remain distinct, and each Relay process
owns a persistent snapshot-cache volume.

| Coolify app | Compose file | Authority services |
|---|---|---|
| `solmara-lab` | `compose.coolify.yaml` | Visitor Center, portal, scenario runner, static metadata, child-benefit evidence composer |
| `solmara-lab-interior` | `compose.coolify.interior.yaml` | CRA and NIA public Relay + private consultation Relay + Notary, PostgreSQL |
| `solmara-lab-social-development` | `compose.coolify.social-development.yaml` | SRO and Programme public Relay + private consultation Relay + Notary, PostgreSQL |
| `solmara-lab-labour-pensions` | `compose.coolify.labour-pensions.yaml` | SIPF public Relay + private consultation Relay + Notary, PostgreSQL |
| `solmara-lab-agriculture` | `compose.coolify.agriculture.yaml` | NAgDI public Relay + private consultation Relay + Notary, PostgreSQL |
| `solmara-lab-esignet` | `compose.coolify.esignet.yaml` | eSignet, eSignet UI and edge, eSignet PostgreSQL and Redis, seed jobs |
| `solmara-lab-wallet` | `compose.coolify.walt.yaml` | Walt holder wallet demonstrator and its backing services |

The child-benefit evidence composer retains the service identifier
`child-benefit-federator` for existing routes. It calls the CRA, NIA, SRO, and
Programme authority Notaries and combines their responses. It is not a Notary,
does not own Notary correctness state, and does not change the six-pair
topology.

Hosted Compose files follow these rules:

- Coolify owns public routing, so services have no host port bindings.
- Runtime configuration is checked into the repository and mounted read-only.
  Secret files are not checked in, and no configuration mount is writable.
- Cross-application calls use public HTTPS endpoints. The applications do not
  share a custom Docker network.
- Hosted services run digest-pinned images and do not use `build:` blocks.
- Every authority Notary owns one PostgreSQL database, owner, migrator, and
  runtime role.
- Every public and consultation Relay mounts its own named volume at
  `/var/lib/registry-relay/cache`. A durable materialization publication
  pointer and its immutable Parquet snapshot must survive the same restart.
- Registry Notary has no Redis service or Redis volume. `esignet-redis` belongs
  only to eSignet.

## Authority pairs and endpoints

| Authority | Relay service and endpoint | Notary service and endpoint |
|---|---|---|
| CRA | `cra-civil-relay`, `https://cra-relay.solmara.registrystack.org` | `cra-notary`, `https://cra-notary.solmara.registrystack.org` |
| NIA | `nia-population-relay`, `https://nia-relay.solmara.registrystack.org` | `nia-notary`, `https://nia-notary.solmara.registrystack.org` |
| SRO | `sro-social-relay`, `https://sro-relay.solmara.registrystack.org` | `sro-notary`, `https://sro-notary.solmara.registrystack.org` |
| Programme | `programme-mis-relay`, `https://mosd-programme-relay.solmara.registrystack.org` | `programme-notary`, `https://programme-notary.solmara.registrystack.org` |
| SIPF | `sipf-pensions-relay`, `https://sipf-relay.solmara.registrystack.org` | `sipf-notary`, `https://sipf-notary.solmara.registrystack.org` |
| NAgDI | `nagdi-agriculture-relay`, `https://nagdi-relay.solmara.registrystack.org` | `nagdi-notary`, `https://nagdi-notary.solmara.registrystack.org` |

The other public endpoints are:

| Service | Endpoint |
|---|---|
| Visitor Center | `https://solmara.registrystack.org` |
| Portal | `https://portal.solmara.registrystack.org` |
| Static metadata | `https://metadata.solmara.registrystack.org` |
| Child-benefit evidence composer | `https://child-benefit-federator.solmara.registrystack.org` |
| eSignet | `https://esignet.solmara.registrystack.org` |
| eSignet UI | `https://esignet-ui.solmara.registrystack.org` |
| Walt holder wallet | `https://wallet.solmara.registrystack.org` |

## Image model

Registry Stack Relay and Notary image refs are inputs to the Solmara wrapper
builds. The `release-candidate` workflow requires a Registry Stack candidate
or release tag and accepts only Relay and Notary input digests that match the
committed `versions.env` pins. It also checks out the exact Registry Stack
source commit declared there for release and contract verification. Governed
attribute release is part of the canonical Registry Stack v0.15.2 Relay
image, which the workflow uses directly as the base of the deployable Solmara
Relay wrapper. Solmara does not compile or publish a feature-specific Relay
runtime. The workflow reports immutable digest refs for these Coolify
variables:

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

Before dispatching the workflow, run
`just review-release <registry-stack-tag>` with that same tag. `just review`
remains the no-argument contributor and CI gate.

Use `image@sha256:<digest>` values in Coolify. Do not deploy mutable tags.
`REGISTRY_STACK_PLATFORM` defaults to `linux/amd64`; override it only when the
selected Registry Stack release publishes another platform.

## Configuration and secrets

The six authority projects are the source of Relay and Notary runtime
configuration. Regenerate both local and hosted closures after changing a
project:

```bash
just registry-projects-sync
just registry-projects-runtime-check
```

Hosted Relay does not boot those compiler outputs as unsigned non-local
configuration. Each public and consultation Relay carries its own
instance-bound signed Config Bundle, public trust anchor, and anti-rollback
state, with no private signing key. The public bundle excludes private
consultation artifacts; the consultation bundle contains the complete
consultation closure. Verify that every signed closure still projects exactly
to the compiler output:

```bash
just hosted-relay-bundles-check
```

When a hosted Relay config or artifact changes, keep the private JWK in
1Password and pass its `op://` secret reference, together with the public-only
JWK file, to `scripts/generate-hosted-relay-bundles.py`. Registryctl reads the
private member directly through 1Password CLI without writing it into the
repository or a working-tree file. When multiple 1Password accounts are signed
in, select the account with `OP_ACCOUNT` and use vault and item IDs in the
secret reference so the lookup is unambiguous. Increment
`SOLMARA_RELAY_BUNDLE_SEQUENCE` in `versions.env`, generate into a new staging
directory, review the config and manifest diffs, then replace the committed
bundle set. The generator creates separate public and consultation streams for
each authority, and the verification gates require all twelve bundles to use
that exact sequence. Never commit the private JWK. A first deployment seeds
sequence zero only into an empty matching Relay cache volume; successful Relay
startup audits and persists the signed sequence. Later image rollback cannot
lower that durable sequence. Publish a higher signed sequence for a normal
rollback, or use Registry Relay's reviewed break-glass procedure.

Each authority application needs only the variables referenced by its Compose
file. At minimum, provide:

- The required digest-pinned `SOLMARA_*_IMAGE` refs.
- `SOLMARA_POSTGRES_PASSWORD` and the source database URL used by NIA or SIPF
  when that authority owns a PostgreSQL-backed source projection.
- Three Relay consultation-state credentials per authority: runtime, keyring
  maintenance, and keyring reader.
- Two Notary state credentials per authority: migrator and runtime.
- Separate Relay and Notary audit hash secrets for every authority.
- The client token hashes and signing keys named by that authority's generated
  runtime configuration.
- The Relay audit pseudonym key and consultation-state retention values named
  by the Compose file.

For example, the CRA app uses `CRA_RELAY_POSTGRES_RUNTIME_PASSWORD`,
`CRA_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD`,
`CRA_RELAY_POSTGRES_KEYRING_READER_PASSWORD`,
`CRA_NOTARY_POSTGRES_MIGRATOR_PASSWORD`, and
`CRA_NOTARY_POSTGRES_RUNTIME_PASSWORD`. Other authorities use the same suffixes
with `NIA`, `SRO`, `PROGRAMME`, `SIPF`, or `NAGDI`.

The core application holds only the client tokens it needs to call the six
authority services. It does not receive authority database credentials.
eSignet and Walt credentials stay in their own applications.

Do not print full environment dumps while deploying. Coolify responses can
include secret values when the caller has sensitive read access.

## Workload identity prerequisite

Each hosted authority application runs a loopback-only workload agent that
rotates a five-minute Relay token into its authority-owned named volume. The
Notary runtime and state installer mount that volume read-only and wait for the
agent to become healthy. Private workload JWKs enter only as Coolify production
secrets; they are not present in images, public metadata, or Compose defaults.
A missing, malformed, or expired token keeps the dependent workload unready.

The public half of every hosted workload key is committed at
`metadata/public/.well-known/jwks.json` and served separately at
`https://workload-issuer.solmara.registrystack.org/.well-known/jwks.json`.
Relay tokens use that HTTPS origin as `iss`, while the token agents remain
bound to container loopback. Keep the public JWKS and all corresponding
Coolify private JWKs in one reviewed rotation.

The eSignet application has a separate NIA identity with
`azp=solmara-esignet`, `sub=solmara-esignet`, and exactly the
`population:identity_release` scope. Its agent writes
`solmara-esignet-relay-token` as UID/GID `1001:1001` into an eSignet-owned
volume. The eSignet plugin rereads that file for each Relay request, so normal
rotation does not require an eSignet restart. Do not copy the token itself into
a Coolify environment variable or reuse the NIA Notary identity.

## Coolify application setup

For each application:

1. Select this repository and the exact commit being deployed.
2. Use Docker Compose as the build pack.
3. Select the application's `compose.coolify*.yaml` file.
4. Disable generated domains and shared custom networks.
5. Add only the production variables referenced by that Compose file.
6. Attach domains to the exact service names in the endpoint tables.
7. Deploy authority applications before the edge application.

Run the eSignet seed job once before expecting portal login to pass. The
authority PostgreSQL bootstrap and state-install jobs are idempotent and run as
part of their Compose dependency graph.

## Deployment verification

From a trusted shell with the demo client tokens available through `.env` or
the process environment:

```bash
just hosted-smoke
```

The smoke checks all six Relay and Notary endpoints, authority evidence
journeys, purpose denial, the Visitor Center proxy, and the portal backend.
Set `SOLMARA_HOSTED_SMOKE_BROWSER=1` to add hosted browser coverage.

For each authority, also verify:

1. Relay `/ready` returns success.
2. Notary `/ready` returns success only after its Relay and database checks.
3. One representative authority evidence request succeeds.
4. A wrong-purpose request is denied without returning the prohibited field.
5. Restarting the Notary preserves correctness state and readiness.

## PostgreSQL operations

The bootstrap container creates only the authority keys listed in
`SOLMARA_RELAY_DATABASES` and `SOLMARA_NOTARY_DATABASES`. The serving Relay and
Notary receive runtime credentials only. Schema installation uses dedicated
jobs and never gives migration credentials to a serving process.

Registry Stack v0.15.2 continues using the `v013` Relay state epoch from
`versions.env`; the retained consultation-result schema does not change in
this release. Existing v0.13.0 authority databases remain the active state
plane. Quiesce old Relay writers before cutover and follow the complete
stopped-writer and rollback procedure in
[`notary-postgresql-state.md`](notary-postgresql-state.md).

Back up, restore, and upgrade each Notary database independently. See
[`notary-postgresql-state.md`](notary-postgresql-state.md) for the database map
and recovery sequence. Preserve the eSignet Redis volume separately because it
is outside the Notary state boundary.

## Troubleshooting

### Notary stays unready

Check the matching Relay `/ready`, PostgreSQL health, state-installer exit
status, and workload-token freshness. A Notary intentionally remains unready
when a required Relay profile cannot be verified.

### State installer fails

Confirm that the authority key appears in `SOLMARA_NOTARY_DATABASES`, that both
authority Notary passwords are set, and that the wrapper and product images
come from the same release. Do not pass the migrator URL to the serving Notary.

### Hosted Notary calls a private service name

Regenerate the hosted project closure with `just registry-projects-sync`.
Hosted Relay source URLs must use the public HTTPS domains in the authority
table. A URL such as `http://cra-civil-relay:8080` cannot cross Coolify
applications.

### Coolify routes the wrong container port

Route the Relay hostname to port `8080` on the public Relay service. Route the
Notary hostname to port `8081` in the private consultation Relay namespace.
Never route consultation Relay port `8080`; it is explicitly bound to
`127.0.0.1` for Notary-only access.
