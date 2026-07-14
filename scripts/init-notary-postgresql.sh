#!/usr/bin/env sh
set -eu

# PostgreSQL runs this file while initializing a fresh cluster and Compose
# reruns it as an idempotent bootstrap before schema installation. Each
# allowlisted logical Notary receives an isolated database and owner,
# migration, and runtime roles. Passwords arrive through the deployment
# secret store and are never printed.

provision_notary() {
  key=$1
  migrator_password=$2
  runtime_password=$3
  database="solmara_notary_${key}"
  owner="${database}_owner"
  migrator="${database}_migrator"
  runtime="${database}_runtime"

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database="$database" \
    --set=owner="$owner" \
    --set=migrator="$migrator" \
    --set=runtime="$runtime" \
    --set=migrator_password="$migrator_password" \
    --set=runtime_password="$runtime_password" <<'SQL'
SELECT format(
  'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'owner'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'owner')
\gexec
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'migrator',
  :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'migrator')
\gexec
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'runtime',
  :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'runtime')
\gexec
SELECT format(
  'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'owner'
)
\gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'migrator',
  :'migrator_password'
)
\gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'runtime',
  :'runtime_password'
)
\gexec
SELECT format('GRANT %I TO %I', :'owner', :'migrator')
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_catalog.pg_auth_members AS membership
  JOIN pg_catalog.pg_roles AS granted_role ON granted_role.oid = membership.roleid
  JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = membership.member
  WHERE granted_role.rolname = :'owner' AND member_role.rolname = :'migrator'
)
\gexec
SELECT format('REVOKE %I FROM %I', :'owner', :'runtime')
WHERE EXISTS (
  SELECT 1
  FROM pg_catalog.pg_auth_members AS membership
  JOIN pg_catalog.pg_roles AS granted_role ON granted_role.oid = membership.roleid
  JOIN pg_catalog.pg_roles AS member_role ON member_role.oid = membership.member
  WHERE granted_role.rolname = :'owner' AND member_role.rolname = :'runtime'
)
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'owner')
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database WHERE datname = :'database')
\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'database', :'owner')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I, %I', :'database', :'migrator', :'runtime')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I, %I', :'database', :'migrator', :'runtime')
\gexec
SQL

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
}

for key in ${SOLMARA_NOTARY_DATABASES:-}; do
  case "$key" in
    civil_child_benefit)
      provision_notary "$key" \
        "${CIVIL_CHILD_BENEFIT_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing civil child benefit Notary migrator password}" \
        "${CIVIL_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing civil child benefit Notary runtime password}"
      ;;
    nia_child_benefit)
      provision_notary "$key" \
        "${NIA_CHILD_BENEFIT_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing NIA child benefit Notary migrator password}" \
        "${NIA_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing NIA child benefit Notary runtime password}"
      ;;
    sro_child_benefit)
      provision_notary "$key" \
        "${SRO_CHILD_BENEFIT_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing SRO child benefit Notary migrator password}" \
        "${SRO_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing SRO child benefit Notary runtime password}"
      ;;
    programme_child_benefit)
      provision_notary "$key" \
        "${PROGRAMME_CHILD_BENEFIT_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing programme child benefit Notary migrator password}" \
        "${PROGRAMME_CHILD_BENEFIT_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing programme child benefit Notary runtime password}"
      ;;
    pension)
      provision_notary "$key" \
        "${PENSION_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing pension Notary migrator password}" \
        "${PENSION_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing pension Notary runtime password}"
      ;;
    nagdi)
      provision_notary "$key" \
        "${NAGDI_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing NAgDI Notary migrator password}" \
        "${NAGDI_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing NAgDI Notary runtime password}"
      ;;
    citizen)
      provision_notary "$key" \
        "${CITIZEN_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing citizen Notary migrator password}" \
        "${CITIZEN_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing citizen Notary runtime password}"
      ;;
    citizen_issuer)
      provision_notary "$key" \
        "${CITIZEN_ISSUER_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing citizen issuer Notary migrator password}" \
        "${CITIZEN_ISSUER_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing citizen issuer Notary runtime password}"
      ;;
    *)
      echo "Unsupported SOLMARA_NOTARY_DATABASES entry" >&2
      exit 1
      ;;
  esac
done
