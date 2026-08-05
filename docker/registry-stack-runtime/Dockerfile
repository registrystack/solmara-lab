# syntax=docker/dockerfile:1.7

FROM rust:1.95-trixie@sha256:f49565f188ee00bc2a18dd418183f2c5f23ef7d6e691890517ed341a598f67c3 AS relay-builder
WORKDIR /workspace

COPY . .

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/workspace/target \
    cargo build --release --locked --package registry-relay \
    && install -D -m 0755 target/release/registry-relay /runtime/usr/local/bin/registry-relay \
    && install -D -m 0755 target/release/registry-relay-rhai-worker /runtime/usr/local/bin/registry-relay-rhai-worker \
    && install -D -m 0644 LICENSE /runtime/licenses/registry-relay/LICENSE \
    && mkdir -p \
        /runtime/etc/registry-relay \
        /runtime/var/lib/registry/audit \
        /runtime/var/lib/registry/state \
        /runtime/var/lib/registry-relay/cache \
        /runtime/var/lib/registry-relay/data \
        /runtime/var/log/registry-relay \
    && chown -R 65532:65532 \
        /runtime/etc/registry-relay \
        /runtime/var/lib/registry \
        /runtime/var/lib/registry-relay \
        /runtime/var/log/registry-relay

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS relay

COPY --from=relay-builder /runtime/ /

WORKDIR /var/lib/registry-relay
ENV REGISTRY_RELAY_CONFIG=/etc/registry-relay/config.yaml
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/usr/local/bin/registry-relay", "healthcheck"]
ENTRYPOINT ["/usr/local/bin/registry-relay"]
CMD ["--config", "/etc/registry-relay/config.yaml"]
