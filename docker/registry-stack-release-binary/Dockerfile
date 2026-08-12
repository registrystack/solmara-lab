# syntax=docker/dockerfile:1.7

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS relayctl
COPY --chown=65532:65532 --chmod=0755 relayctl /usr/local/bin/relayctl
ENTRYPOINT ["/usr/local/bin/relayctl"]
