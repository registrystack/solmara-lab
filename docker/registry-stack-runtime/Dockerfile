# syntax=docker/dockerfile:1.7

FROM rust:1.95-trixie@sha256:f49565f188ee00bc2a18dd418183f2c5f23ef7d6e691890517ed341a598f67c3 AS relay-builder
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/workspace/target \
    CARGO_INCREMENTAL=0 CARGO_PROFILE_RELEASE_DEBUG=0 \
    cargo build --release --locked -p registry-relay-v2 -p registry-relayctl \
    && install -D -m 0755 target/release/relay /runtime/usr/local/bin/relay \
    && install -D -m 0755 target/release/relayctl /tooling/usr/local/bin/relayctl \
    && install -D -m 0644 LICENSE /runtime/licenses/relay/LICENSE \
    && mkdir -p /runtime/etc/relay /runtime/var/lib/relay/audit /runtime/var/lib/relay/source \
    && chown -R 65532:65532 /runtime/etc/relay /runtime/var/lib/relay

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775 AS relay
COPY --from=relay-builder /runtime/ /
WORKDIR /var/lib/relay
EXPOSE 8080
ENV RELAY_HEALTHCHECK_URL=http://127.0.0.1:8080/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/usr/local/bin/relay", "healthcheck"]
ENTRYPOINT ["/usr/local/bin/relay"]
CMD ["serve", "--runtime", "/etc/relay/runtime.yaml"]

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd AS relayctl
COPY --from=relay-builder /tooling/ /
ENTRYPOINT ["/usr/local/bin/relayctl"]
