#!/usr/bin/env sh
set -eu

ssl_src=/run/solmara-postgres-ssl
ssl_dst=/var/lib/postgresql/server-ssl

mkdir -p "$ssl_dst"
cp "$ssl_src/server.crt" "$ssl_dst/server.crt"
cp "$ssl_src/server.key" "$ssl_dst/server.key"
chown postgres:postgres "$ssl_dst/server.crt" "$ssl_dst/server.key"
chmod 0644 "$ssl_dst/server.crt"
chmod 0600 "$ssl_dst/server.key"

ready_file=/tmp/solmara-postgres-provisioned
rm -f "$ready_file"

/usr/local/bin/docker-entrypoint.sh "$@" &
postgres_pid=$!

stop_postgres() {
  kill -TERM "$postgres_pid" 2>/dev/null || true
}
trap stop_postgres INT TERM

until pg_isready --quiet --host 127.0.0.1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"; do
  if ! kill -0 "$postgres_pid" 2>/dev/null; then
    wait "$postgres_pid"
    exit $?
  fi
  sleep 1
done

if ! /usr/local/bin/solmara-provision-postgresql.sh; then
  stop_postgres
  wait "$postgres_pid" || true
  exit 1
fi

touch "$ready_file"
wait "$postgres_pid"
