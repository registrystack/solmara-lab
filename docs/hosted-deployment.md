# Hosted deployment

Deploy the authority-cell reset only from the exact Registry Stack release
recorded in `versions.env`. Relay, Evidence, and Mint must use their official
Registry Stack OCI images pinned by digest. Solmara-owned images are also
digest-pinned, while the local Relayctl helper is assembled from its
checksum-verified release asset. A missing, floating, or mismatched pin stops
deployment.

The sanitized hosted image manifest carries `REGISTRY_RELAY_IMAGE`,
`SOLMARA_EVIDENCE_IMAGE`, and `SOLMARA_MINT_IMAGE` unchanged from
`versions.env`. Compose consumes those exact full references. The separate
Relay digest field remains release-verification evidence only and is not a
deployment input.

Registry Stack v0.20.0 remains immutable and does not contain the Evidence
capability required by this lab. v0.20.1 contains the required runtime
capabilities but does not publish official Evidence and Mint OCI images.
Registry Stack v0.21.0 is the first coherent release with all three official
runtime images; the lab currently pins v0.22.0 from that line. Do not move a
release, substitute a floating source reference, or recreate those runtime
images in Solmara.

## Release package precondition

Before the first release-candidate build, an organization owner must provision
these two public, anonymously pullable GitHub Container Registry packages and
grant the repository's GitHub Actions workflow write access:

- `ghcr.io/registrystack/solmara-lab-authority-provisioner`
- `ghcr.io/registrystack/solmara-lab-transit-signer`

The Registry Stack release owns the public `relay`, `evidence`, and `mint`
packages. Solmara only reads those upstream digest references from
`versions.env`; its workflow neither rebuilds nor republishes them. The
authority provisioner contains the reviewed contracts and deterministic
publications. The Transit signer contains only the signer runtime. Release
handoff records the immutable digest of every upstream and Solmara-owned image.
Do not reuse an unrelated package or deploy a mutable tag.

## Authority topology

The hosted topology contains five Relay V2 services, six independently signed
Evidence cells, one shared lab Mint, and the programme application. The optional
eSignet profile uses the NIA Relay lookup.

Evidence hosts are:

- `cra-evidence.solmara.registrystack.org`
- `nia-evidence.solmara.registrystack.org`
- `sro-evidence.solmara.registrystack.org`
- `mosd-programme-evidence.solmara.registrystack.org`
- `sipf-evidence.solmara.registrystack.org`
- `nagdi-evidence.solmara.registrystack.org`

Shared authority state lives at fixed absolute host paths of the form
`/data/solmara-authority-cells/<cell>/<role>` rather than in named volumes.
Coolify rewrites every named volume reference to `{app_uuid}_{key}` and does not
consult `external: true`, so a named volume would give each application a
private copy of its own instead of the one the provisioner writes. The 34 shared
paths are:

| Owner | Paths | Contents |
|---|---:|---|
| Shared Mint | 3 | Runtime, secrets, and Transit socket |
| Five Relays | 10 | One runtime and one mutable source path per authority |
| Six Evidence cells | 21 | Runtime, secrets, and Transit socket per cell, plus the CRA, NIA, and SRO immutable-extract paths |

`compose.coolify.provision.yaml` is a dedicated operator-only application. It
runs only the one-shot target provisioners and is the sole writer of every
shared path except the seven Transit sockets.

Every application that touches this state root must run on the same Docker host.
The paths are node-local and no Compose file can enforce placement, so a
provisioner on one server and a consumer on another would resolve the same path
to two different empty directories. Co-locating the provision, signer, core, and
four authority applications is a deployment precondition.

Each ministry runs its own signer application, which creates and owns the
Transit socket paths of its cells and runs one isolated signer per cell:

| Application | File | Signers |
|---|---|---|
| `solmara-lab-mint-signer` | `compose.coolify.signers.mint.yaml` | Mint |
| `solmara-lab-interior-signers` | `compose.coolify.signers.interior.yaml` | CRA, NIA |
| `solmara-lab-social-signers` | `compose.coolify.signers.social-development.yaml` | SRO, MOSD |
| `solmara-lab-pensions-signers` | `compose.coolify.signers.labour-pensions.yaml` | SIPF |
| `solmara-lab-agriculture-signers` | `compose.coolify.signers.agriculture.yaml` | NAGDI |

Compose scopes a private issuer key to its own signer container, but a Coolify
application environment is a boundary Compose cannot express. Splitting the
signers by ministry keeps each private signing key out of every environment but
its owner's. The provision
application never receives a private issuer signing key. Runtime applications
attach the runtime, source, secret, extract, and Transit paths read-only. Each
runtime application owns the writable audit volumes for its services and
initializes their permissions without reading or replacing existing audit
records.

Docker Compose injects an environment-backed secret after creating its target
container and rejects that operation when the root filesystem is read-only.
Relay provisioners and Transit initializers remain read-only. The one-shot
Evidence and Mint provisioners and the non-root signer processes instead mount
`/run/secrets` as tmpfs. They remain networkless with no new privileges; signer
processes also run with every Linux capability dropped. Secret values are not
placed in container environment variables. The provisioner copies only the
required non-signing runtime secrets into each authority's isolated secret
path; private issuer signing keys remain confined to signer tmpfs.

## Mint clients

The shared Mint registers nine clients under the common lab audience. Eight are
least-authority source clients, each limited to its named operation:

- `cra-pension-evidence`
- `cra-citizen-evidence`
- `mosd-child-benefit-evidence`
- `sipf-pension-evidence`
- `sipf-survivor-evidence`
- `nagdi-voucher-evidence`
- `nagdi-livestock-evidence`
- `nia-esignet`

The ninth client, `solmara-demo`, belongs to the programme application and is
used to request assertions from the authority Evidence cells. The shared Mint
is a lab convenience, not production tenancy guidance.

## Secret boundary

Create deployment secrets for these classes without placing their values in a
Compose file, repository file, build log, or delivery record:

- one private and public signing JWK pair for Mint and for each of the six
  Evidence issuers;
- one private and public client JWK pair for each of the nine Mint clients;
- authority-specific Relay audit HMAC keys, plus cursor HMAC keys for the Relay
  contracts that require cursors;
- Mint and Evidence audit HMAC keys;
- one subject-binding HMAC key for each Evidence cell;
- the programme federator token;
- when eSignet is enabled, its database credential, KYC-token and PSUT HMAC
  secrets, KYC keystore credentials, and portal OIDC client key.

Each signing private JWK is projected only to its dedicated signer. That signer
also receives the matching public half and refuses startup unless it is the
exact projection of the private key. A Mint
client private JWK is installed only for its client owner, and an
authority-scoped one-shot provisioner may write it only into that owner's
secret path. Inject public JWK halves into the provisioner and their matching
signers only; the provisioner writes
the issuer projections and Mint client registrations into the generated
runtime material. No runtime receives another authority's client private key.

Never commit a private key, token, generated database, generated Relay package,
runtime bundle, or audit log.

## Immutable extract lifecycle

CRA birth, NIA population, and SRO poverty use immutable SQLite extracts. The
hosted provisioner creates the initial checked publication and reuses the exact
active filename on a restart. It never overwrites an active extract in place.

To publish a later checkpoint, override the matching direct-cell provisioner
service command with:

```text
publish-extract --target <cra|nia|sro>-evidence --assets /opt/solmara-hosted-assets --runtime-output /provisioned/runtime --extract-output /provisioned/extracts
```

The operation validates the current binding, appends the checked publication
under a fresh immutable filename, preserves the old file, and atomically
rebinds only that cell's runtime configuration. Restart only the matching
Evidence cell after the operation succeeds. The running cell continues to read
the old mounted extract until that restart. A malformed, metadata-mismatched,
or non-newer publication fails closed.

## Deployment order

Deploy the reset alongside the existing deployment in this order:

1. Record the old deployment's exact image references, routes, and retained
   volume names. Do not attach an old writer to a new source path.
2. Deploy `compose.coolify.provision.yaml`. Require every one-shot provisioner
   to complete successfully.
3. Deploy the five signer applications. They share no state and may deploy in
   any order. Require every Transit initializer to complete successfully and
   each application's `<group>-signers-ready` barrier to complete, which happens
   only once all seven signers across the five applications are healthy.

   If a previous deployment ran the single aggregate signer application, stop it
   before deploying these five. It still owns the seven live Transit sockets, and
   a signer refuses to start on a socket that accepts a connection rather than
   removing another process's listener, so every replacement would exit and no
   readiness barrier could complete. Rollback reverses this: stop all five, then
   start the aggregate application.
4. Deploy the shared Mint, programme services, portal, Visitor Center, and
   static metadata from `compose.coolify.yaml`. Require Mint health, discovery,
   and JWKS to pass before starting a Relay, because every Relay validates the
   permanent Mint issuer during startup. Do not send programme requests yet.
5. Deploy the authority runtime applications from
   `compose.coolify.interior.yaml`,
   `compose.coolify.social-development.yaml`,
   `compose.coolify.labour-pensions.yaml`, and
   `compose.coolify.agriculture.yaml`. Confirm all five Relays and all six
   Evidence cells are ready on the private routes.
6. Run the hosted programme, denial, JWKS, source-label, redaction, and UI smoke
   against the new routes before changing public routing.
7. If required for this deployment, add `compose.coolify.esignet.yaml` and run
   the citizen-login smoke through the NIA Relay V2 lookup.
8. Switch programme authority URLs and public metadata routing only after every
   required smoke passes. Disable the superseded services, but retain their
   volumes and exact deployment references for recovery.

Rollback restores routing to the old services and their retained volumes. It
does not reuse a new Relay V2 database with an older binary. Removing a
superseded service or volume is a separate approved cleanup.

## Hosted acceptance

Acceptance is based on live hosted behavior, not inferred from local tests. It
requires:

- child benefit to compose four independently signed assertions and return the
  expected five positive concepts;
- pension to compose CRA and SIPF assertions without disclosing cause of death
  or unrelated civil data;
- both agriculture journeys to succeed through their NAgDI lookups;
- wrong-purpose and unauthorized calls to fail generically;
- the portal to prove authority URL selection, per-authority JWKS verification,
  source-type labels, and redaction;
- the Visitor Center to show the publisher, six Evidence cells, five Relays,
  shared Mint, and programme application;
- when the optional profile is deployed, eSignet login to complete through the
  NIA Relay V2 lookup.

Attach only sanitized pass or fail results and public artifact identities to
the delivery record. Do not attach selectors, source rows, tokens, private
audit material, secrets, deployment logs, or private release evidence.
