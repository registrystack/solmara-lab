ARG REGISTRY_RELAY_IMAGE=ghcr.io/registrystack/registry-relay@sha256:00681003d06667cde377e15640a3825eec97aca26f486cde2e9f5013ef56819e
ARG VOLUME_INIT_IMAGE=busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
FROM ${VOLUME_INIT_IMAGE} AS volume-init
FROM ${REGISTRY_RELAY_IMAGE}

COPY --from=volume-init /bin/busybox /bin/busybox
COPY ministries /var/lib/solmara/ministries
COPY config/hosted-relay-bundles /etc/solmara/hosted-relay-bundles
COPY config/postgres/ssl/server.crt /etc/solmara/postgres/root.crt
