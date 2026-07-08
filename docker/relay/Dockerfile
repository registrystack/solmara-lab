ARG REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/registry-relay@sha256:93e194500a3500ba3f6331d5a0a9a3069127c48a709beccb083a5fcbdbc3ec61
FROM ${REGISTRY_RELAY_IMAGE}

COPY ministries /var/lib/solmara/ministries
COPY hosted/ministries /var/lib/solmara/ministries
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
