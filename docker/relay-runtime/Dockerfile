# syntax=docker/dockerfile:1.7

ARG REGISTRY_RELAY_IMAGE

FROM rust:1.95-trixie@sha256:f49565f188ee00bc2a18dd418183f2c5f23ef7d6e691890517ed341a598f67c3 AS builder
WORKDIR /workspace/registry-stack

COPY . .

ARG REGISTRY_RELAY_FEATURES
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/workspace/registry-stack/target \
    cargo build --release --locked \
      --package registry-relay \
      --features "${REGISTRY_RELAY_FEATURES}" \
    && cp target/release/registry-relay /usr/local/bin/registry-relay \
    && cp target/release/registry-relay-rhai-worker /usr/local/bin/registry-relay-rhai-worker

FROM ${REGISTRY_RELAY_IMAGE}

ARG REGISTRY_RELAY_IMAGE
ARG REGISTRY_STACK_SOURCE_COMMIT
ARG REGISTRY_RELAY_FEATURES
LABEL org.opencontainers.image.base.name="${REGISTRY_RELAY_IMAGE}"
LABEL org.opencontainers.image.revision="${REGISTRY_STACK_SOURCE_COMMIT}"
LABEL org.registrystack.solmara.relay-features="${REGISTRY_RELAY_FEATURES}"

COPY --from=builder /usr/local/bin/registry-relay /usr/local/bin/registry-relay
COPY --from=builder /usr/local/bin/registry-relay-rhai-worker /usr/local/bin/registry-relay-rhai-worker
