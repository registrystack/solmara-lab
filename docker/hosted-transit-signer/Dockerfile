# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv

FROM python@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df AS dependencies
WORKDIR /build
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && sed -i '/^pyyaml==/d' requirements.txt \
    && pip install --no-cache-dir --prefix=/runtime -r requirements.txt

FROM python@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY --from=dependencies /runtime /usr/local
COPY --chmod=0555 scripts/hosted-transit-signer.py /opt/solmara-transit-signer/hosted-transit-signer.py
COPY --chmod=0555 scripts/local-transit-proxy.py /opt/solmara-transit-signer/local-transit-proxy.py
USER 65532:65532
ENTRYPOINT ["python", "/opt/solmara-transit-signer/hosted-transit-signer.py"]
