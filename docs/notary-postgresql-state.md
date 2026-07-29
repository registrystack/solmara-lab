# Notary PostgreSQL state

Solmara Lab runs exactly one Registry Notary beside each authority Relay. Each
Notary owns an independent PostgreSQL database and role set. PostgreSQL servers
may be shared within a local or hosted Compose application, but databases,
owners, migrators, and runtime roles are never shared between Notaries.

| Authority | Public Relay / private consultation Relay | Notary service | Relay state database | Notary database | Local Relay / Notary |
|---|---|---|---|---|---|
| Civil Registration Authority (CRA) | `cra-civil-relay` / `cra-civil-relay-consultation` | `cra-notary` | `solmara_relay_cra_consultation_v015` | `solmara_notary_cra` | `4311` / `4325` |
| National Identity Agency (NIA) | `nia-population-relay` / `nia-population-relay-consultation` | `nia-notary` | `solmara_relay_nia_consultation_v015` | `solmara_notary_nia` | `4312` / `4326` |
| Social Registry Office (SRO) | `sro-social-relay` / `sro-social-relay-consultation` | `sro-notary` | `solmara_relay_sro_consultation_v015` | `solmara_notary_sro` | `4313` / `4327` |
| Programme MIS | `programme-mis-relay` / `programme-mis-relay-consultation` | `programme-notary` | `solmara_relay_programme_consultation_v015` | `solmara_notary_programme` | `4314` / `4328` |
| Social Insurance and Pensions Fund (SIPF) | `sipf-pensions-relay` / `sipf-pensions-relay-consultation` | `sipf-notary` | `solmara_relay_sipf_consultation_v015` | `solmara_notary_sipf` | `4315` / `4322` |
| National Agricultural Data Institute (NAgDI) | `nagdi-agriculture-relay` / `nagdi-agriculture-relay-consultation` | `nagdi-notary` | `solmara_relay_nagdi_consultation_v015` | `solmara_notary_nagdi` | `4316` / `4323` |

The local topology shares one PostgreSQL server for developer convenience.
Hosted authority applications keep the same database boundaries within their
own PostgreSQL volume. The runtime role for an authority follows the form
`solmara_notary_<authority>_runtime`; the owner and migrator roles use the same
authority key.

The named `postgres-data` volume is mounted directly at PostgreSQL's
`/var/lib/postgresql/data` data directory. Keep that exact mount target while
the topology uses PostgreSQL 16. Mounting the parent directory allows the
image's declared data-directory volume to become anonymous, which would discard
authority state when Compose removes the PostgreSQL container. `just down`
followed by `just up` preserves the named data volume; only `just reset`
deliberately deletes it.

Run `just notary-state-restart-proof` after a representative live smoke. The
gate records the PostgreSQL system identifier and every correctness-table row
count in all six authority databases, performs the exact `just down` and
`just up` lifecycle, rejects anonymous PGDATA mounts, compares the state before
any new requests are sent, and reruns `state doctor` for every Notary.

## Startup and readiness

The startup order is intentional:

1. `registry-postgresql-bootstrap` creates or attests only the databases and
   roles listed by that Compose application.
2. Each private consultation Relay bootstraps its PostgreSQL state before its
   serving process starts.
3. The authority workload issuer publishes the verification keys and writes a
   short-lived Notary token. Local public and consultation Relay namespaces
   have separate loopback-only issuer processes; hosted Relays validate against
   the separately served HTTPS JWKS.
4. Each `<authority>-notary-state-install` job applies or attests the released
   Notary schema with the migrator role once its database and token file are
   ready.
5. The matching Notary starts with only its runtime database role and a
   read-only workload-token mount. The public Relay starts independently from
   the consultation state plane.

Each Notary shares only its private consultation Relay's network namespace.
The consultation Relay binds `127.0.0.1:8080` and Notary binds port `8081`, so
the consultation path has a direct loopback trust boundary. The separately
routable public Relay never receives Notary consultation traffic. Readiness
remains unavailable until PostgreSQL state and required Relay source profiles
are usable.

Relay snapshot caches are not Notary correctness state, but they are durable
Relay restart data. Each public and consultation Relay mounts a distinct
`/var/lib/registry-relay/cache` volume so one process's materialization pointer
never outlives its referenced immutable snapshot.

Inspect one local pair without exposing credentials:

```bash
curl --fail http://127.0.0.1:4311/ready
curl --fail http://127.0.0.1:4325/ready
docker compose run --rm --no-deps cra-notary \
  --config /etc/registry-notary/notary.yaml state doctor
```

Substitute the ports and service name from the table for another authority.

## Backup and restore

Back up each Notary database as a complete unit. Do not dump individual tables
or merge databases from different authorities.

Before an upgrade or recovery drill:

1. Record the deployed Registry Notary image digest and config revision.
2. Take a consistent PostgreSQL backup of every authority Notary database.
3. Back up the database role credentials in the secret manager, separately
   from the database backup.
4. Verify restore into an isolated PostgreSQL server with the same major
   version.
5. Run `state doctor` with the restored runtime configuration before sending
   traffic.

For a restore, stop all writers for that authority, restore the complete
database, restore the matching credentials, deploy the recorded Notary image
and config, and run `state doctor`. Reopen traffic only after readiness and a
representative authority scenario pass.

## Upgrades and rollback

Treat the schema installer as a release step, not a serving-container
permission. For each authority:

1. Stop or drain its Notary replicas.
2. Take and verify a complete database backup.
3. Deploy the target PostgreSQL and Notary images.
4. Let the authority's state installer finish successfully.
5. Start serving replicas, run `state doctor`, and verify `/ready` and an
   authority scenario.

Do not run an older Notary binary against a forward-migrated schema. If an
upgrade cannot be completed, restore the pre-upgrade database and the matching
image and configuration together. The normative product procedure is the
[Registry Notary PostgreSQL state operations guide](https://github.com/registrystack/registry-stack/blob/main/products/notary/docs/postgresql-state-operations.md).

### Registry Stack v0.15.2 cache-persistence cutover

The v0.15.2 deployment introduces distinct persistent cache volumes for every
public and consultation Relay. The earlier hosted topology persisted
PostgreSQL materialization publication pointers while keeping their immutable
Parquet snapshots in ephemeral container storage. After container
replacement, a surviving pointer can therefore name a snapshot that no
longer exists.

Solmara establishes a recoverable boundary with
`REGISTRY_RELAY_STATE_EPOCH=v015` in `versions.env`. The bootstrap creates new
Relay databases and roles without deleting or rewriting the `v013` state.
For the cutover:

1. Stop new authority traffic and stop every `v013` Relay writer.
2. Back up the `v013` databases and retain the matching images and
   configuration.
3. Deploy the v0.15.2 Compose closure. Bootstrap creates the `v015` Relay
   databases, then each Relay publishes fresh materializations into its
   persistent cache.
4. Require every Relay and Notary `/ready` check, the complete smoke suite,
   and the restart-persistence proof before reopening traffic.

Keep the `v013` databases quiesced during the rollback window. Rollback means
restoring the matching pre-cutover deployment as one unit. Never point the
new cache-backed deployment at a `v013` database whose referenced snapshot
files were not preserved.

### Registry Stack v0.13.0 cutover

Registry Stack v0.13.0 removes `provenance.consent` from the exact retained
Relay result contract. Old and v0.13.0 Relay binaries must not share a
consultation state plane. Solmara enforces that boundary with
`REGISTRY_RELAY_STATE_EPOCH=v013` in `versions.env`. The PostgreSQL bootstrap
uses the epoch in every Relay database and role name and runs idempotently on
fresh and existing clusters.

For the v0.10.0 to v0.13.0 cutover:

1. Stop new authority traffic and stop every old Relay and Notary writer.
2. Drain retained terminal replay lifetimes, then back up every old Relay and
   Notary database with its exact image and configuration refs.
3. Deploy the v0.13.0 Compose closure. The bootstrap creates the new `v013`
   Relay databases and roles, and each Relay bootstraps its empty state plane.
   The Notary installers migrate or attest the existing Notary databases.
4. Require every Relay and Notary `/ready` check, `state doctor`, the complete
   local or hosted smoke, and the PostgreSQL restart-persistence proof before
   reopening traffic.

Keep the old, unsuffixed Relay databases quiesced until the rollback window
closes. A rollback restores the pre-upgrade Notary backups and matching
v0.10.0 images and configs, then reconnects the old Relay binaries only to the
old Relay databases. Never point a v0.13.0 Relay at an unsuffixed database or
an old Relay at a `v013` database.

The local topology deliberately pins PostgreSQL 16 and its
`/var/lib/postgresql/data` mount layout. Do not change the image tag to 18 in
place. PostgreSQL 18's official container layout mounts the parent
`/var/lib/postgresql` directory and places data under a major-specific child.
The [official PostgreSQL container documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata)
defines the exact paths. A move to 18 therefore requires a stopped-writer
`pg_upgrade` or verified dump/restore into a newly created PostgreSQL 18 volume,
followed by all six `state doctor` checks and the restart-persistence gate.
Recreating the container against the PostgreSQL 16 volume without that
procedure is not an upgrade.

## Redis retirement

Registry Notary has no production Redis dependency in Solmara Lab. The pre-1.0
cutover deliberately has no importer or dual-write mode. Old purpose-specific
Notary and citizen-issuer Redis volumes are retired and must not be attached to
the six authority Notaries.

`esignet-redis` in `compose.esignet.yaml` and
`compose.coolify.esignet.yaml` belongs to eSignet. It is not Notary correctness
state and remains part of the eSignet deployment.
