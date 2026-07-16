ARG REGISTRY_NOTARY_IMAGE=ghcr.io/registrystack/registry-notary@sha256:a1206ca0e6059c3bd88b84060a9be28cf5399abae6c94a9bf1d545cdaeefc639
FROM ${REGISTRY_NOTARY_IMAGE}

COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
