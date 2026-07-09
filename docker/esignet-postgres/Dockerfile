ARG POSTGRES_IMAGE=postgres:16
FROM ${POSTGRES_IMAGE}

COPY config/esignet/init.sql /docker-entrypoint-initdb.d/init.sql
