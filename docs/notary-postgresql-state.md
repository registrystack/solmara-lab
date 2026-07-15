# Notary PostgreSQL state

Solmara Lab runs exactly one Registry Notary beside each authority Relay. Each
Notary owns an independent PostgreSQL database and role set. PostgreSQL servers
may be shared within a local or hosted Compose application, but databases,
owners, migrators, and runtime roles are never shared between Notaries.

| Authority | Relay service | Notary service | Database | Local Relay / Notary |
|---|---|---|---|---|
| Civil Registration Authority (CRA) | `cra-civil-relay` | `cra-notary` | `solmara_notary_cra` | `4311` / `4325` |
| National Identity Agency (NIA) | `nia-population-relay` | `nia-notary` | `solmara_notary_nia` | `4312` / `4326` |
| Social Registry Office (SRO) | `sro-social-relay` | `sro-notary` | `solmara_notary_sro` | `4313` / `4327` |
| Programme MIS | `programme-mis-relay` | `programme-notary` | `solmara_notary_programme` | `4314` / `4328` |
| Social Insurance and Pensions Fund (SIPF) | `sipf-pensions-relay` | `sipf-notary` | `solmara_notary_sipf` | `4315` / `4322` |
| National Agricultural Data Institute (NAgDI) | `nagdi-agriculture-relay` | `nagdi-notary` | `solmara_notary_nagdi` | `4316` / `4323` |

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
2. Each `<authority>-notary-state-install` job applies or attests the released
   Notary schema with the migrator role.
3. The authority Relay becomes healthy and its workload issuer supplies a
   short-lived Relay token to the authority's workload volume.
4. The matching Notary starts with only its runtime database role and a
   read-only workload-token mount.

Each Notary shares its Relay's network namespace. Relay binds port `8080` and
Notary binds port `8081`, so the pair has a direct loopback trust boundary.
Readiness remains unavailable until PostgreSQL state and required Relay source
profiles are usable.

Relay snapshot caches are not Notary correctness state, but they are durable
Relay restart data. Each authority Relay mounts a separate
`/var/lib/registry-relay/cache` volume so its PostgreSQL materialization pointer
never outlives the referenced immutable snapshot.

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
