ARG REGISTRY_NOTARY_IMAGE=ghcr.io/registrystack/registry-notary@sha256:a1206ca0e6059c3bd88b84060a9be28cf5399abae6c94a9bf1d545cdaeefc639
FROM ${REGISTRY_NOTARY_IMAGE}

COPY runtime/registry-projects/hosted/cra-civil/notary/notary.yaml /etc/solmara/registry-projects/hosted/cra-civil/notary/notary.yaml
COPY runtime/registry-projects/hosted/nia-population/notary/notary.yaml /etc/solmara/registry-projects/hosted/nia-population/notary/notary.yaml
COPY runtime/registry-projects/hosted/sro-social/notary/notary.yaml /etc/solmara/registry-projects/hosted/sro-social/notary/notary.yaml
COPY runtime/registry-projects/hosted/mosd-programme/notary/notary.yaml /etc/solmara/registry-projects/hosted/mosd-programme/notary/notary.yaml
COPY runtime/registry-projects/hosted/sipf-pensions/notary/notary.yaml /etc/solmara/registry-projects/hosted/sipf-pensions/notary/notary.yaml
COPY runtime/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml /etc/solmara/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
