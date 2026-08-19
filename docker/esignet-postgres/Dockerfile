ARG POSTGRES_IMAGE=postgres@sha256:9479eac93922431e8a512b016d7362ae264f4ba139f840891b51f02931e450db
FROM ${POSTGRES_IMAGE}

COPY config/esignet/init.sql /docker-entrypoint-initdb.d/init.sql
