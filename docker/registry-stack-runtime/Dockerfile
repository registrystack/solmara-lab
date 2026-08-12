# syntax=docker/dockerfile:1.7

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS evidence

COPY --chown=65532:65532 evidence-root/ /
COPY --chmod=0755 evidence /usr/local/bin/evidence

WORKDIR /var/lib/registry-evidence
ENV REGISTRY_EVIDENCE_RUNTIME=/etc/registry-evidence/runtime.yaml
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/evidence"]
CMD ["serve"]

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS mint

COPY --chown=65532:65532 mint-root/ /
COPY --chmod=0755 mint /usr/local/bin/mint

ENV MINT_CONFIG=/etc/registry-mint/config.yaml
EXPOSE 8081
ENTRYPOINT ["/usr/local/bin/mint"]
CMD ["serve"]
