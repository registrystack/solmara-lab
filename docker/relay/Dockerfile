ARG REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/registry-relay@sha256:00681003d06667cde377e15640a3825eec97aca26f486cde2e9f5013ef56819e
FROM ${REGISTRY_RELAY_IMAGE}

COPY ministries /var/lib/solmara/ministries
COPY runtime/registry-projects/hosted/cra-civil/relay /etc/solmara/registry-projects/hosted/cra-civil/relay
COPY runtime/registry-projects/hosted/nia-population/relay /etc/solmara/registry-projects/hosted/nia-population/relay
COPY runtime/registry-projects/hosted/sro-social/relay /etc/solmara/registry-projects/hosted/sro-social/relay
COPY runtime/registry-projects/hosted/mosd-programme/relay /etc/solmara/registry-projects/hosted/mosd-programme/relay
COPY runtime/registry-projects/hosted/sipf-pensions/relay /etc/solmara/registry-projects/hosted/sipf-pensions/relay
COPY runtime/registry-projects/hosted/nagdi-agriculture/relay /etc/solmara/registry-projects/hosted/nagdi-agriculture/relay
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
