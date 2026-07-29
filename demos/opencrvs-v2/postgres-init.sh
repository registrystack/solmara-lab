#!/usr/bin/env sh
set -eu

# Provision only the four database identities required by Relay consultation
# state. Values arrive through the disposable demo environment and are never
# printed or copied into generated Registry Stack configuration.

for name in \
  POSTGRES_ADMIN_PASSWORD \
  OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD \
  OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD \
  OPENCRVS_RELAY_POSTGRES_READER_PASSWORD
do
  case "$name" in
    POSTGRES_ADMIN_PASSWORD)
      value=${POSTGRES_ADMIN_PASSWORD:-}
      ;;
    OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD)
      value=${OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD:-}
      ;;
    OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD)
      value=${OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD:-}
      ;;
    OPENCRVS_RELAY_POSTGRES_READER_PASSWORD)
      value=${OPENCRVS_RELAY_POSTGRES_READER_PASSWORD:-}
      ;;
  esac
  case "$value" in
    "" | *[!A-Za-z0-9_-]*)
      echo "$name must contain only bounded URL-safe characters" >&2
      exit 1
      ;;
  esac
  if [ "${#value}" -lt 32 ] || [ "${#value}" -gt 128 ]; then
    echo "$name is outside its length bound" >&2
    exit 1
  fi
done

export PGPASSWORD="$POSTGRES_ADMIN_PASSWORD"

psql \
  --quiet \
  --set=ON_ERROR_STOP=1 \
  --host=opencrvs-db \
  --username=opencrvs_admin \
  --dbname=postgres \
  --set=runtime_password="$OPENCRVS_RELAY_POSTGRES_RUNTIME_PASSWORD" \
  --set=maintenance_password="$OPENCRVS_RELAY_POSTGRES_MAINTENANCE_PASSWORD" \
  --set=reader_password="$OPENCRVS_RELAY_POSTGRES_READER_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  'opencrvs_demo_owner'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'opencrvs_demo_owner'
)
\gexec
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  role_name,
  role_password
)
FROM (VALUES
  ('opencrvs_demo_runtime', :'runtime_password'),
  ('opencrvs_demo_keyring_maintenance', :'maintenance_password'),
  ('opencrvs_demo_keyring_reader', :'reader_password')
) AS requested(role_name, role_password)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = requested.role_name
)
\gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  role_name,
  role_password
)
FROM (VALUES
  ('opencrvs_demo_runtime', :'runtime_password'),
  ('opencrvs_demo_keyring_maintenance', :'maintenance_password'),
  ('opencrvs_demo_keyring_reader', :'reader_password')
) AS requested(role_name, role_password)
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', 'opencrvs_demo', 'opencrvs_demo_owner')
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'opencrvs_demo'
)
\gexec
SELECT format('REVOKE %I FROM %I', granted.rolname, member.rolname)
FROM pg_catalog.pg_auth_members AS membership
JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid
JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
WHERE granted.rolname = 'opencrvs_demo_owner'
  AND member.rolname IN (
    'opencrvs_demo_runtime',
    'opencrvs_demo_keyring_maintenance',
    'opencrvs_demo_keyring_reader'
  )
\gexec
REVOKE ALL ON DATABASE opencrvs_demo FROM PUBLIC;
GRANT CONNECT, CREATE ON DATABASE opencrvs_demo TO opencrvs_demo_owner;
GRANT CONNECT ON DATABASE opencrvs_demo
  TO opencrvs_demo_runtime,
     opencrvs_demo_keyring_maintenance,
     opencrvs_demo_keyring_reader;
SQL

psql \
  --quiet \
  --set=ON_ERROR_STOP=1 \
  --host=opencrvs-db \
  --username=opencrvs_admin \
  --dbname=opencrvs_demo <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
