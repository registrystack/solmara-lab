ARG REGISTRY_NOTARY_IMAGE=ghcr.io/registrystack/registry-notary@sha256:1cce41247a18f70cb7ff4276bdeb5a16c1e641a9ed7951be8f612daaf35ab87b
FROM ${REGISTRY_NOTARY_IMAGE}

COPY runtime/registry-projects/hosted/cra-civil/notary/notary.yaml /etc/solmara/registry-projects/hosted/cra-civil/notary/notary.yaml
COPY runtime/registry-projects/hosted/nia-population/notary/notary.yaml /etc/solmara/registry-projects/hosted/nia-population/notary/notary.yaml
COPY runtime/registry-projects/hosted/sro-social/notary/notary.yaml /etc/solmara/registry-projects/hosted/sro-social/notary/notary.yaml
COPY runtime/registry-projects/hosted/mosd-programme/notary/notary.yaml /etc/solmara/registry-projects/hosted/mosd-programme/notary/notary.yaml
COPY runtime/registry-projects/hosted/sipf-pensions/notary/notary.yaml /etc/solmara/registry-projects/hosted/sipf-pensions/notary/notary.yaml
COPY runtime/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml /etc/solmara/registry-projects/hosted/nagdi-agriculture/notary/notary.yaml
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
