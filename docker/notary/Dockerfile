ARG REGISTRY_NOTARY_IMAGE=ghcr.io/registrystack/registry-notary@sha256:6848ad62789bd6e5a1af4262f85e9a0110bea9ed8e3f9297adab19cb62f8f297
FROM ${REGISTRY_NOTARY_IMAGE}

COPY runtime/registry-projects/hosted/cra-civil/notary/notary.yaml /etc/solmara/registry-projects/hosted/cra-civil/notary/notary.yaml
COPY runtime/registry-projects/hosted/nia-population/notary/notary.yaml /etc/solmara/registry-projects/hosted/nia-population/notary/notary.yaml
COPY runtime/registry-projects/hosted/sro-social/notary/notary.yaml /etc/solmara/registry-projects/hosted/sro-social/notary/notary.yaml
COPY runtime/registry-projects/hosted/mosd-programme/notary/notary.yaml /etc/solmara/registry-projects/hosted/mosd-programme/notary/notary.yaml
COPY runtime/registry-projects/hosted/sipf-pensions/notary/notary.yaml /etc/solmara/registry-projects/hosted/sipf-pensions/notary/notary.yaml
COPY runtime/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml /etc/solmara/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
