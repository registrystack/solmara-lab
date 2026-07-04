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

exec /usr/local/bin/docker-entrypoint.sh "$@"
