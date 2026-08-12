#!/usr/bin/env sh
set -eu

# PostgreSQL runs this file while initializing a fresh cluster and Compose
# reruns it as an idempotent bootstrap before schema installation. It creates
# only the least-privilege source readers needed by the hosted Relays.

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
