# syntax=docker/dockerfile:1.7

FROM alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS evidence-download
ARG REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL
ARG REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256
RUN test -n "$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL" && \
    test -n "$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256" && \
    wget -q -O /evidence "$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_URL" && \
    printf '%s  %s\n' "$REGISTRY_STACK_RELEASE_EVIDENCE_ASSET_SHA256" /evidence | sha256sum -c - && \
    chmod 0755 /evidence

FROM alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS mint-download
ARG REGISTRY_STACK_RELEASE_MINT_ASSET_URL
ARG REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256
RUN test -n "$REGISTRY_STACK_RELEASE_MINT_ASSET_URL" && \
    test -n "$REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256" && \
    wget -q -O /mint "$REGISTRY_STACK_RELEASE_MINT_ASSET_URL" && \
    printf '%s  %s\n' "$REGISTRY_STACK_RELEASE_MINT_ASSET_SHA256" /mint | sha256sum -c - && \
    chmod 0755 /mint

FROM alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS relayctl-download
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256
RUN test -n "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL" && \
    test -n "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" && \
    wget -q -O /relayctl "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL" && \
    printf '%s  %s\n' "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" /relayctl | sha256sum -c - && \
    chmod 0755 /relayctl

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS evidence
COPY --from=evidence-download --chown=65532:65532 /evidence /usr/local/bin/evidence
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/evidence"]

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS mint
COPY --from=mint-download --chown=65532:65532 /mint /usr/local/bin/mint
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/mint"]

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS relayctl
COPY --from=relayctl-download --chown=65532:65532 /relayctl /usr/local/bin/relayctl
ENTRYPOINT ["/usr/local/bin/relayctl"]
