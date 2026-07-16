#!/usr/bin/env sh
set -eu

# PostgreSQL runs this file while initializing a fresh cluster and Compose
# reruns it as an idempotent bootstrap before schema installation. Each
# allowlisted authority receives separate Relay consultation and Notary
# databases. Passwords arrive through the deployment secret store and are
# never printed.

provision_relay() {
  key=$1
  runtime_password=$2
  maintenance_password=$3
  reader_password=$4
  database="solmara_relay_${key}_consultation"
  owner="${database}_owner"
  runtime="${database}_runtime"
  maintenance="${database}_keyring_maintenance"
  reader="${database}_keyring_reader"

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database="$database" \
    --set=owner="$owner" \
    --set=runtime="$runtime" \
    --set=maintenance="$maintenance" \
    --set=reader="$reader" \
    --set=runtime_password="$runtime_password" \
    --set=maintenance_password="$maintenance_password" \
    --set=reader_password="$reader_password" <<'SQL'
SELECT format(
  'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'owner'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'owner')
\gexec
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  role_name,
  role_password
)
FROM (VALUES
  (:'runtime', :'runtime_password'),
  (:'maintenance', :'maintenance_password'),
  (:'reader', :'reader_password')
) AS requested(role_name, role_password)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = requested.role_name)
\gexec
SELECT format(
  'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
  :'owner'
)
\gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  role_name,
  role_password
)
FROM (VALUES
  (:'runtime', :'runtime_password'),
  (:'maintenance', :'maintenance_password'),
  (:'reader', :'reader_password')
) AS requested(role_name, role_password)
\gexec
SELECT format('REVOKE %I FROM %I', granted.rolname, member.rolname)
FROM pg_catalog.pg_auth_members AS membership
JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid
JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
WHERE member.rolname IN (:'owner', :'runtime', :'maintenance', :'reader')
\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'owner')
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database WHERE datname = :'database')
\gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'database', :'owner')
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database')
\gexec
SELECT format(
  'REVOKE ALL ON DATABASE %I FROM %I, %I, %I, %I',
  :'database', :'owner', :'runtime', :'maintenance', :'reader'
)
\gexec
SELECT format('GRANT CONNECT, CREATE ON DATABASE %I TO %I', :'database', :'owner')
\gexec
SELECT format(
  'GRANT CONNECT ON DATABASE %I TO %I, %I, %I',
  :'database', :'runtime', :'maintenance', :'reader'
)
\gexec
SQL

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
}

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

provision_source_reader() {
  key=$1
  password=$2
  role="solmara_source_${key}_reader"

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=database="$POSTGRES_DB" \
    --set=role="$role" \
    --set=password="$password" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'role',
  :'password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'role')
\gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'role',
  :'password'
)
\gexec
SELECT format('REVOKE %I FROM %I', granted.rolname, member.rolname)
FROM pg_catalog.pg_auth_members AS membership
JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid
JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
WHERE member.rolname = :'role'
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'database', :'role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database', :'role')
\gexec
SQL

  psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=role="$role" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', :'role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'role')
\gexec
SQL

  case "$key" in
    nia)
      psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        --set=role="$role" <<'SQL'
SELECT format('GRANT SELECT ON TABLE public.population_person TO %I', :'role')
\gexec
SQL
      ;;
    sipf)
      psql --quiet --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
        --set=role="$role" <<'SQL'
SELECT format(
  'GRANT SELECT ON TABLE public.sipf_pension_payment, public.sipf_survivor_benefit TO %I',
  :'role'
)
\gexec
SQL
      ;;
    *)
      echo "Unsupported source reader" >&2
      exit 1
      ;;
  esac
}

for key in ${SOLMARA_SOURCE_READER_DATABASES:-}; do
  case "$key" in
    nia)
      provision_source_reader "$key" \
        "${NIA_SOURCE_POSTGRES_READER_PASSWORD:?missing NIA source reader password}"
      ;;
    sipf)
      provision_source_reader "$key" \
        "${SIPF_SOURCE_POSTGRES_READER_PASSWORD:?missing SIPF source reader password}"
      ;;
    *)
      echo "Unsupported SOLMARA_SOURCE_READER_DATABASES entry" >&2
      exit 1
      ;;
  esac
done

for key in ${SOLMARA_RELAY_DATABASES:-}; do
  case "$key" in
    cra)
      provision_relay "$key" \
        "${CRA_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing CRA Relay runtime password}" \
        "${CRA_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing CRA Relay keyring maintenance password}" \
        "${CRA_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing CRA Relay keyring reader password}"
      ;;
    nia)
      provision_relay "$key" \
        "${NIA_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing NIA Relay runtime password}" \
        "${NIA_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing NIA Relay keyring maintenance password}" \
        "${NIA_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing NIA Relay keyring reader password}"
      ;;
    sro)
      provision_relay "$key" \
        "${SRO_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing SRO Relay runtime password}" \
        "${SRO_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing SRO Relay keyring maintenance password}" \
        "${SRO_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing SRO Relay keyring reader password}"
      ;;
    programme)
      provision_relay "$key" \
        "${PROGRAMME_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing programme Relay runtime password}" \
        "${PROGRAMME_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing programme Relay keyring maintenance password}" \
        "${PROGRAMME_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing programme Relay keyring reader password}"
      ;;
    sipf)
      provision_relay "$key" \
        "${SIPF_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing SIPF Relay runtime password}" \
        "${SIPF_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing SIPF Relay keyring maintenance password}" \
        "${SIPF_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing SIPF Relay keyring reader password}"
      ;;
    nagdi)
      provision_relay "$key" \
        "${NAGDI_RELAY_POSTGRES_RUNTIME_PASSWORD:?missing NAgDI Relay runtime password}" \
        "${NAGDI_RELAY_POSTGRES_KEYRING_MAINTENANCE_PASSWORD:?missing NAgDI Relay keyring maintenance password}" \
        "${NAGDI_RELAY_POSTGRES_KEYRING_READER_PASSWORD:?missing NAgDI Relay keyring reader password}"
      ;;
    *)
      echo "Unsupported SOLMARA_RELAY_DATABASES entry" >&2
      exit 1
      ;;
  esac
done

for key in ${SOLMARA_NOTARY_DATABASES:-}; do
  case "$key" in
    cra)
      provision_notary "$key" \
        "${CRA_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing CRA Notary migrator password}" \
        "${CRA_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing CRA Notary runtime password}"
      ;;
    nia)
      provision_notary "$key" \
        "${NIA_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing NIA Notary migrator password}" \
        "${NIA_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing NIA Notary runtime password}"
      ;;
    sro)
      provision_notary "$key" \
        "${SRO_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing SRO Notary migrator password}" \
        "${SRO_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing SRO Notary runtime password}"
      ;;
    programme)
      provision_notary "$key" \
        "${PROGRAMME_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing programme Notary migrator password}" \
        "${PROGRAMME_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing programme Notary runtime password}"
      ;;
    sipf)
      provision_notary "$key" \
        "${SIPF_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing SIPF Notary migrator password}" \
        "${SIPF_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing SIPF Notary runtime password}"
      ;;
    nagdi)
      provision_notary "$key" \
        "${NAGDI_NOTARY_POSTGRES_MIGRATOR_PASSWORD:?missing NAgDI Notary migrator password}" \
        "${NAGDI_NOTARY_POSTGRES_RUNTIME_PASSWORD:?missing NAgDI Notary runtime password}"
      ;;
    *)
      echo "Unsupported SOLMARA_NOTARY_DATABASES entry" >&2
      exit 1
      ;;
  esac
done
