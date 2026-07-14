ARG POSTGRES_IMAGE=postgres:16-alpine
FROM ${POSTGRES_IMAGE}

COPY ministries/interior-population/fixtures /docker-entrypoint-initdb.d
COPY scripts/init-notary-postgresql.sh /docker-entrypoint-initdb.d/010-init-notary-postgresql.sh
COPY scripts/postgres-entrypoint.sh /usr/local/bin/solmara-postgres-entrypoint.sh
COPY config/postgres/ssl /run/solmara-postgres-ssl

RUN chmod 0755 /usr/local/bin/solmara-postgres-entrypoint.sh \
    /docker-entrypoint-initdb.d/010-init-notary-postgresql.sh
