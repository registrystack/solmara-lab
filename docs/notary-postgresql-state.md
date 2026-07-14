# Notary PostgreSQL state

Solmara Lab gives each logical Registry Notary an independent PostgreSQL
database and an independent owner, migration, and runtime role. PostgreSQL
servers may be shared inside one authority application, but databases and
roles are never shared between Notaries. Only replicas of the same logical
Notary may use the same database.

| Notary | Database | Runtime role |
|---|---|---|
| CRA child benefit | `solmara_notary_civil_child_benefit` | `solmara_notary_civil_child_benefit_runtime` |
| NIA child benefit | `solmara_notary_nia_child_benefit` | `solmara_notary_nia_child_benefit_runtime` |
| SRO child benefit | `solmara_notary_sro_child_benefit` | `solmara_notary_sro_child_benefit_runtime` |
| Programme child benefit | `solmara_notary_programme_child_benefit` | `solmara_notary_programme_child_benefit_runtime` |
| Pension | `solmara_notary_pension` | `solmara_notary_pension_runtime` |
| NAgDI | `solmara_notary_nagdi` | `solmara_notary_nagdi_runtime` |
| Citizen services | `solmara_notary_citizen` | `solmara_notary_citizen_runtime` |
| Citizen OID4VCI issuer | `solmara_notary_citizen_issuer` | `solmara_notary_citizen_issuer_runtime` |

The matching owner and migrator role names replace the `_runtime` suffix with
`_owner` and `_migrator`. Owner roles cannot log in. Migrator roles may assume
only their matching owner. Runtime roles receive only the fixed Notary
transaction-function privileges installed by Registry Notary.

## Local startup and diagnosis

`just gen-secrets` generates separate migrator and runtime passwords for all
eight databases, the citizen issuer sensitive-state key, and the local TLS
certificate. `docker compose up` then performs three ordered steps:

1. The idempotent PostgreSQL bootstrap creates or attests the allowlisted
   databases and restricted roles, including on an existing cluster, and
   applies configured role-password rotation.
2. Each `*-state-install` job applies or attests the released Notary schema
   with its migrator role.
3. The matching Notary starts only after the installer exits successfully.

Notary startup repeats the runtime-role and schema attestation before binding a
listener. A missing database, failed installer, wrong role, incompatible
schema, or unavailable TLS root therefore prevents readiness.

Run the product doctor against a running local database without exposing a
migration credential:

```bash
docker compose run --rm --no-deps civil-child-benefit-notary \
  --config /etc/registry-notary/child-benefit-civil.yaml state doctor
```

Substitute the target service and its mounted config path for another Notary.
Do not print `docker compose config` or a full environment dump because the
rendered output contains database credentials and signing material.

## Hosted installation and upgrades

Each authority Compose application owns a PostgreSQL volume and provisions
only the databases listed in its `SOLMARA_NOTARY_DATABASES` value. An
idempotent `notary-postgresql-bootstrap` job creates or attests the database
and role boundaries before the one-shot state installers run. Both job types
have `restart: "no"`; serving Notaries depend on their successful completion.
The migration URL exists only in the matching installer container. It is not
present in the serving Notary container.

Use a stopped-writer upgrade:

1. Remove the affected Notary from traffic and stop all its replicas.
2. Take and verify a whole-database backup. Preserve the role-provisioning
   inputs, deployed Registry Notary release, and sensitive-state key version
   with the recovery evidence.
3. Deploy the target PostgreSQL and Notary images. Let the matching installer
   apply the forward migration.
4. Run `state doctor`, start one serving instance, and verify readiness and a
   realistic evaluation or issuance canary.
5. Start any identical replicas only after the canary succeeds.

Never run an older Notary binary against a forward-migrated schema. Restore the
matching database backup, role definitions, application version, and
sensitive-state key together for rollback.

## Backup and recovery

Back up every Notary database as a complete unit. Do not dump individual
correctness tables. Logical dumps should use the matching migrator connection,
assume the matching owner role, and use `--no-owner --no-acl`. Keep database
URLs in a restricted libpq service file and password file, not in command-line
arguments.

After restore into an isolated writable primary:

1. Recreate the exact owner, migrator, and runtime role contract.
2. Restore the whole database and the matching citizen issuer sensitive-state
   key version when applicable.
3. Run the released `state install` command to rebind the role identities.
4. Run `state doctor` and a restart canary before admitting traffic.
5. Quarantine a potentially stale restore until replay identifiers, nonces,
   evaluations, idempotency records, preauthorization state, and quota windows
   that may be missing have expired. A possibly missing revocation cannot be
   repaired by waiting.

The authoritative install, backup, restore, stale-restore, retention, and
upgrade contract is the Registry Notary
[PostgreSQL state operations guide](https://github.com/registrystack/registry-stack/blob/main/products/notary/docs/postgresql-state-operations.md).

## Redis cutover

This pre-1.0 change deliberately has no Redis importer or dual-write mode.
Stop every old Notary writer and wait the longest configured request or token
lifetime, at least one hour for the quota window, before starting the
PostgreSQL-backed deployment. Solmara Notary credential status is disabled, so
there are no revocation rows to migrate. Only after PostgreSQL installation,
doctor, restart, and scenario checks pass may the old Notary Redis volume and
credentials be deleted.

The `esignet-redis` services in `compose.esignet.yaml` and
`compose.coolify.esignet.yaml` remain. They are eSignet-owned cache state and
are outside the Notary cutover.
