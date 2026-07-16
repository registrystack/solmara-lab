ARG REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/registry-relay@sha256:81d0b97e60560159a0f77ee10008a859f4e5dc15fc70fcb2c2fb50f8f190617f
FROM ${REGISTRY_RELAY_IMAGE}

COPY ministries /var/lib/solmara/ministries
COPY runtime/registry-projects/hosted/cra-civil/relay /etc/solmara/registry-projects/hosted/cra-civil/relay
COPY runtime/registry-projects/hosted/nia-population/relay /etc/solmara/registry-projects/hosted/nia-population/relay
COPY runtime/registry-projects/hosted/sro-social/relay /etc/solmara/registry-projects/hosted/sro-social/relay
COPY runtime/registry-projects/hosted/mosd-programme/relay /etc/solmara/registry-projects/hosted/mosd-programme/relay
COPY runtime/registry-projects/hosted/sipf-pensions/relay /etc/solmara/registry-projects/hosted/sipf-pensions/relay
COPY runtime/registry-projects/hosted/nagdi-agriculture/relay /etc/solmara/registry-projects/hosted/nagdi-agriculture/relay
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
