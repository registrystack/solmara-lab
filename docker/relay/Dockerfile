ARG REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/registry-relay@sha256:81d0b97e60560159a0f77ee10008a859f4e5dc15fc70fcb2c2fb50f8f190617f
FROM ${REGISTRY_RELAY_IMAGE}

COPY ministries /var/lib/solmara/ministries
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
