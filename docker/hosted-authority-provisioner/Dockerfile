# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df
ARG ASSET_PYTHON_IMAGE=python:3.12-slim-trixie@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d
ARG ALPINE_IMAGE=alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256

FROM ${ALPINE_IMAGE} AS relayctl-download
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL
ARG REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256
RUN test -n "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL" && \
    test -n "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" && \
    wget -q -O /relayctl "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_URL" && \
    printf '%s  %s\n' "$REGISTRY_STACK_RELEASE_RELAYCTL_ASSET_SHA256" /relayctl | sha256sum -c - && \
    chmod 0755 /relayctl

FROM ${UV_IMAGE} AS uv

FROM ${ASSET_PYTHON_IMAGE} AS assets
ENV PYTHONDONTWRITEBYTECODE=1
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=relayctl-download /relayctl /usr/local/bin/relayctl
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o /requirements.txt && \
    pip install --no-cache-dir -r /requirements.txt && rm /requirements.txt
COPY generator/solmara_lab/__init__.py generator/solmara_lab/generate.py generator/solmara_lab/publisher.py ./generator/solmara_lab/
COPY relays ./relays
COPY evidence/cells ./evidence/cells
COPY evidence/mint.yaml ./evidence/mint.yaml
COPY scripts/hosted-runtime-assets.py ./scripts/hosted-runtime-assets.py
RUN python scripts/hosted-runtime-assets.py build \
      --root /workspace \
      --output /opt/solmara-hosted-assets \
      --relayctl /usr/local/bin/relayctl

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o /requirements.txt && \
    pip install --no-cache-dir -r /requirements.txt && rm /requirements.txt
COPY --from=assets /opt/solmara-hosted-assets /opt/solmara-hosted-assets
COPY scripts/hosted-runtime-assets.py /app/scripts/hosted-runtime-assets.py
COPY scripts/provision-hosted-runtime.py /app/scripts/provision-hosted-runtime.py
ENTRYPOINT ["python", "/app/scripts/provision-hosted-runtime.py"]
